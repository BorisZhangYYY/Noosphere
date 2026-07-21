import { ArrowRight, BookOpenText, CloudArrowUp, MagnifyingGlass, Path } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
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
  const { t } = useTranslation();
  const query = useQuery({ queryKey: ["articles"], queryFn: api.listArticles });
  const taxonomyQuery = useQuery({ queryKey: ["taxonomy"], queryFn: api.getTaxonomy });
  const [categoryFilter, setCategoryFilter] = useState("");
  const articles = query.data?.articles ?? [];
  const visibleArticles = categoryFilter ? articles.filter((article) => article.classification?.tag_name === categoryFilter || article.classification?.subtag_name === categoryFilter) : articles;
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
          <input type="search" placeholder={t("library.search")} aria-label={t("library.search")} disabled />
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
          <button type="button" className={!categoryFilter ? "active" : ""} onClick={() => setCategoryFilter("")}>{t("library.allTags")}</button>
          {taxonomyQuery.data.tags.map((tag) => <div className="taxonomy-family" key={tag.id}><button type="button" className={categoryFilter === tag.name ? "active" : ""} title={tag.description} onClick={() => setCategoryFilter(tag.name)}>{tag.name}</button>{tag.children.map((child) => <button type="button" className={categoryFilter === child.name ? "active child" : "child"} title={child.description} onClick={() => setCategoryFilter(child.name)} key={child.id}>{child.name}</button>)}</div>)}
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
