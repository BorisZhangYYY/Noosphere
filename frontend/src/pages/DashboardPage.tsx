import { ArrowClockwise, ArrowCounterClockwise, ArrowRight, BookOpenText, CaretDown, CaretUp, Check, CheckSquare, Circle, CloudArrowUp, MagnifyingGlass, Path, SpinnerGap, Square, Trash, WarningCircle } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import { StatusBadge } from "../components/StatusBadge";
import { localizedPlatformLabel } from "../localization";
import type { ArticleSummary, TrashedArticle } from "../types";

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

function ArticleRow({ article, selected, onSelect }: { article: ArticleSummary; selected: boolean; onSelect: () => void }) {
  const { t, i18n } = useTranslation();
  const platformLabel = localizedPlatformLabel(article.platform, article.platformLabel, t);
  return (
    <div className={`article-row-wrap${selected ? " article-row-selected" : ""}`}>
      <button className="article-select-button" type="button" aria-label={t("library.selectArticle", { title: article.title })} aria-pressed={selected} onClick={onSelect}>
        {selected ? <CheckSquare size={18} weight="fill" /> : <Square size={18} />}
      </button>
      <Link className="article-row" to={`/articles/${encodeURIComponent(article.id)}`}>
        <span className="source-monogram" aria-hidden="true">{platformLabel.slice(0, 1).toUpperCase()}</span>
        <span className="article-primary">
          <strong>{article.title}</strong>
          <span>{article.collection?.collection_path.length ? article.collection.collection_path.map((item) => item.name).join(" / ") : article.author || platformLabel}</span>
        </span>
        <span className="article-source">{platformLabel}</span>
        <span className="article-captured">{relativeTime(article.capturedAt, i18n.resolvedLanguage ?? i18n.language, t("common.unknown"), t("library.justNow"))}</span>
        <StatusBadge status={article.status} />
        <ArrowRight size={18} className="row-arrow" />
      </Link>
    </div>
  );
}

function TrashRow({ article, selected, onSelect, onRestore, onDelete }: {
  article: TrashedArticle;
  selected: boolean;
  onSelect: () => void;
  onRestore: () => void;
  onDelete: () => void;
}) {
  const { t, i18n } = useTranslation();
  return (
    <div className={`trash-row${selected ? " trash-row-selected" : ""}`}>
      <button className="article-select-button trash-select-button" type="button" aria-label={t("library.selectArticle", { title: article.title })} aria-pressed={selected} onClick={onSelect}>
        {selected ? <CheckSquare size={18} weight="fill" /> : <Square size={18} />}
      </button>
      <span className="source-monogram"><Trash size={16} /></span>
      <span className="article-primary"><strong>{article.title}</strong><span>{article.details.platformLabel || article.url}</span></span>
      <span className="trash-deleted-at">{relativeTime(article.deletedAt, i18n.resolvedLanguage ?? i18n.language, t("common.unknown"), t("library.justNow"))}</span>
      <span className="trash-row-actions">
        <button className="button-secondary compact-button" type="button" onClick={onRestore}><ArrowCounterClockwise size={15} />{t("library.restore")}</button>
        <button className="icon-danger-button" type="button" aria-label={t("library.deletePermanently")} onClick={onDelete}><Trash size={16} /></button>
      </span>
    </div>
  );
}

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["articles", i18n.resolvedLanguage], queryFn: api.listArticles });
  const trashQuery = useQuery({ queryKey: ["article-trash"], queryFn: api.listTrashedArticles });
  const jobsQuery = useQuery({
    queryKey: ["capture-jobs"],
    queryFn: api.listCaptureJobs,
    refetchInterval: (jobQuery) => jobQuery.state.data?.jobs.some((job) => job.status === "queued" || job.status === "running") ? 1200 : false
  });
  const [search, setSearch] = useState("");
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const [view, setView] = useState<"library" | "trash">("library");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [pendingAction, setPendingAction] = useState<{ action: "trash" | "restore" | "delete"; ids: string[] } | null>(null);
  const articles = query.data?.articles ?? [];
  const jobs = jobsQuery.data?.jobs ?? [];
  const trashedArticles = trashQuery.data?.articles ?? [];
  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleArticles = articles.filter((article) => {
    const searchMatches = !normalizedSearch || [article.title, article.author ?? "", article.platformLabel, ...(article.searchTerms ?? [])].join(" ").toLocaleLowerCase().includes(normalizedSearch);
    return searchMatches;
  });
  const reviewed = articles.filter((article) => article.status === "reviewed" || article.status === "uploaded").length;
  const uploaded = articles.filter((article) => article.status === "uploaded").length;
  const needsAttention = articles.filter((article) => article.status === "failed").length;
  const mutation = useMutation({
    mutationFn: async ({ action, ids }: { action: "trash" | "restore" | "delete"; ids: string[] }) => {
      if (action === "trash") return api.trashArticles(ids);
      if (action === "restore") return api.restoreTrashedArticles(ids);
      return api.permanentlyDeleteTrashedArticles(ids);
    },
    onSuccess: async () => {
      setPendingAction(null);
      setSelectedIds(new Set());
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["articles"] }),
        queryClient.invalidateQueries({ queryKey: ["article-trash"] }),
        queryClient.invalidateQueries({ queryKey: ["collections"] })
      ]);
    }
  });
  const retryMutation = useMutation({
    mutationFn: api.retryCaptureJob,
    onSuccess: async (job) => {
      setExpandedJob(job.id);
      await queryClient.invalidateQueries({ queryKey: ["capture-jobs"] });
    }
  });
  const visibleIds = view === "library" ? visibleArticles.map((article) => article.id) : trashedArticles.map((article) => article.id);
  const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));

  function toggleSelected(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function switchView(nextView: "library" | "trash") {
    setView(nextView);
    setSelectedIds(new Set());
    setSearch("");
  }

  return (
    <div className="page dashboard-page">
      <header className="page-header dashboard-header">
        <div>
          <p className="context-label">{t("overview.eyebrow")}</p>
          <h1>{t("overview.title")}</h1>
          <p>{t("overview.description")}</p>
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

      <section className="workspace-surface dashboard-jobs">
        <div className="section-heading dashboard-section-heading">
          <div><h2>{t("pipeline.currentTitle")}</h2><p>{t("pipeline.currentDescription")}</p></div>
          <span className="dashboard-section-count">{jobs.length}</span>
        </div>
        {jobsQuery.isLoading && <LoadingPanel />}
        {jobsQuery.isError && <ErrorPanel message={(jobsQuery.error as Error).message} />}
        {!jobsQuery.isLoading && !jobs.length && (
          <div className="dashboard-jobs-empty"><Check size={17} />{t("pipeline.emptyTitle")}</div>
        )}
        {jobs.slice(0, 6).map((job) => {
          const expanded = expandedJob === job.id;
          const detail = job.error || job.result?.hpath || (
            job.status === "recovered"
              ? t("pipeline.recoveredHelp")
              : job.status === "awaiting_review"
                ? t("pipeline.awaitingReviewHelp")
                : t("pipeline.working")
          );
          return (
            <article className={`dashboard-job${expanded ? " expanded" : ""}`} key={job.id}>
              <button type="button" aria-expanded={expanded} onClick={() => setExpandedJob(expanded ? null : job.id)}>
                <span className={`dashboard-job-state dashboard-job-${job.status}`}>
                  {job.status === "failed"
                    ? <WarningCircle size={18} />
                    : ["succeeded", "awaiting_review", "recovered"].includes(job.status)
                      ? <Check size={17} />
                      : <Circle size={15} />}
                </span>
                <span><strong>{job.url}</strong><small>{detail}</small></span>
                <em>{t(`status.${job.status}`)}</em>
                {expanded ? <CaretUp size={15} /> : <CaretDown size={15} />}
              </button>
              {expanded && (
                <div className="dashboard-job-details">
                  {job.events.slice(-5).map((event) => (
                    <div key={event.id}><time>{new Date(event.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</time><span>{t(event.message)}</span></div>
                  ))}
                  <div className="dashboard-job-actions">
                    {job.status === "failed" && (
                      <button
                        className="button-primary compact-button"
                        type="button"
                        disabled={retryMutation.isPending}
                        onClick={() => retryMutation.mutate(job.id)}
                      >
                        {retryMutation.isPending && retryMutation.variables === job.id
                          ? <SpinnerGap className="spin" size={15} />
                          : <ArrowClockwise size={15} />}
                        {t("pipeline.retry")}
                      </button>
                    )}
                    {job.articleId && <Link to={`/articles/${encodeURIComponent(job.articleId)}`}>{t("pipeline.openArticle")}<ArrowRight size={15} /></Link>}
                  </div>
                  {retryMutation.isError && retryMutation.variables === job.id && (
                    <p className="job-action-error" role="alert">{(retryMutation.error as Error).message}</p>
                  )}
                </div>
              )}
            </article>
          );
        })}
      </section>

      <section className="workspace-surface recent-section">
        <div className="section-heading">
          <div><h2>{t("library.recentTitle")}</h2><p>{t("library.recentDescription")}</p></div>
          <div className="library-view-switch" role="tablist" aria-label={t("library.viewMode")}>
            <button type="button" role="tab" aria-selected={view === "library"} className={view === "library" ? "active" : ""} onClick={() => switchView("library")}>{t("library.activeArticles")}<small>{articles.length}</small></button>
            <button type="button" role="tab" aria-selected={view === "trash"} className={view === "trash" ? "active" : ""} onClick={() => switchView("trash")}><Trash size={14} />{t("library.recycleBin")}<small>{trashedArticles.length}</small></button>
          </div>
        </div>
        <div className="library-selection-bar">
          <button type="button" className="selection-toggle" onClick={() => setSelectedIds(allVisibleSelected ? new Set() : new Set(visibleIds))}>
            {allVisibleSelected ? <CheckSquare size={18} weight="fill" /> : <Square size={18} />}
            {allVisibleSelected ? t("library.clearSelection") : t("library.selectAll")}
          </button>
          <span>{selectedIds.size ? t("library.selectedCount", { count: selectedIds.size }) : view === "library" ? t("library.total", { count: visibleArticles.length }) : t("library.trashTotal", { count: trashedArticles.length })}</span>
          {selectedIds.size > 0 && (
            <span className="selection-actions">
              {view === "trash" && <button className="button-secondary compact-button" type="button" onClick={() => setPendingAction({ action: "restore", ids: [...selectedIds] })}><ArrowCounterClockwise size={15} />{t("library.restoreSelected")}</button>}
              <button className="button-danger compact-button" type="button" onClick={() => setPendingAction({ action: view === "library" ? "trash" : "delete", ids: [...selectedIds] })}><Trash size={15} />{view === "library" ? t("library.moveToTrash") : t("library.deletePermanently")}</button>
            </span>
          )}
        </div>
        {view === "library" && <div className="article-list-header" aria-hidden="true">
          <span>{t("library.columnArticle")}</span><span>{t("library.columnSource")}</span><span>{t("library.columnCaptured")}</span><span>{t("library.columnStatus")}</span>
        </div>}
        {view === "library" && query.isLoading && <LoadingPanel />}
        {view === "library" && query.isError && <ErrorPanel message={(query.error as Error).message} />}
        {view === "trash" && trashQuery.isLoading && <LoadingPanel />}
        {view === "trash" && trashQuery.isError && <ErrorPanel message={(trashQuery.error as Error).message} />}
        {view === "library" && !query.isLoading && !query.isError && articles.length === 0 && (
          <div className="empty-state">
            <div className="empty-illustration"><BookOpenText size={34} /></div>
            <h3>{t("library.emptyTitle")}</h3>
            <p>{t("library.emptyDescription")}</p>
          </div>
        )}
        {view === "trash" && !trashQuery.isLoading && !trashQuery.isError && trashedArticles.length === 0 && (
          <div className="empty-state">
            <div className="empty-illustration"><Trash size={32} /></div>
            <h3>{t("library.trashEmptyTitle")}</h3>
            <p>{t("library.trashEmptyDescription")}</p>
          </div>
        )}
        {view === "library" && visibleArticles.map((article) => <ArticleRow article={article} selected={selectedIds.has(article.id)} onSelect={() => toggleSelected(article.id)} key={article.id} />)}
        {view === "trash" && trashedArticles.map((article) => (
          <TrashRow
            article={article}
            selected={selectedIds.has(article.id)}
            onSelect={() => toggleSelected(article.id)}
            onRestore={() => setPendingAction({ action: "restore", ids: [article.id] })}
            onDelete={() => setPendingAction({ action: "delete", ids: [article.id] })}
            key={article.id}
          />
        ))}
      </section>

      {pendingAction && (
        <div className="dialog-layer modal-root-layer" role="presentation" onMouseDown={() => !mutation.isPending && setPendingAction(null)}>
          <section className="article-confirm-dialog library-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="library-confirm-title" onMouseDown={(event) => event.stopPropagation()}>
            <span className="confirm-dialog-icon"><WarningCircle size={24} /></span>
            <div>
              <h2 id="library-confirm-title">{t(`library.confirm.${pendingAction.action}Title`, { count: pendingAction.ids.length })}</h2>
              <p>{t(`library.confirm.${pendingAction.action}Description`, { count: pendingAction.ids.length })}</p>
              {mutation.isError && <p className="dialog-error" role="alert">{(mutation.error as Error).message}</p>}
              <div className="dialog-actions">
                <button className="button-secondary" type="button" disabled={mutation.isPending} onClick={() => setPendingAction(null)}>{t("common.cancel")}</button>
                <button className={pendingAction.action === "restore" ? "button-primary" : "button-danger"} type="button" disabled={mutation.isPending} onClick={() => mutation.mutate(pendingAction)}>
                  {mutation.isPending && <SpinnerGap className="spin" size={17} />}
                  {t(`library.confirm.${pendingAction.action}Action`)}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
