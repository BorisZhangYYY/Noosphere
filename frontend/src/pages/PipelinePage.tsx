import { CaretDown, CaretUp, Check, Circle, CloudArrowDown, MagicWand, TerminalWindow, UploadSimple, WarningCircle } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { api } from "../api";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import { StatusBadge } from "../components/StatusBadge";
import { localizedPlatformLabel } from "../localization";

const stages = [
  { labelKey: "pipeline.stageCapture", icon: CloudArrowDown },
  { labelKey: "pipeline.stageReview", icon: MagicWand },
  { labelKey: "pipeline.stageUpload", icon: UploadSimple }
];

export function PipelinePage() {
  const { t } = useTranslation();
  const [expandedJob, setExpandedJob] = useState<string | null>(null);
  const query = useQuery({ queryKey: ["articles"], queryFn: api.listArticles });
  const jobsQuery = useQuery({
    queryKey: ["capture-jobs"],
    queryFn: api.listCaptureJobs,
    refetchInterval: (jobQuery) => jobQuery.state.data?.jobs.some((job) => job.status === "queued" || job.status === "running") ? 1200 : false
  });
  const articles = query.data?.articles ?? [];
  const jobs = jobsQuery.data?.jobs ?? [];

  return (
    <div className="page pipeline-page">
      <header className="page-header">
        <div><p className="context-label">{t("pipeline.eyebrow")}</p><h1>{t("pipeline.title")}</h1><p>{t("pipeline.description")}</p></div>
      </header>
      <div className="pipeline-stage-map" aria-label={t("pipeline.stagesLabel")}>
        {stages.map(({ labelKey, icon: Icon }, index) => (
          <div key={labelKey} className="pipeline-stage">
            <span><Icon size={22} /></span><strong>{t(labelKey)}</strong>
            {index < stages.length - 1 && <i />}
          </div>
        ))}
      </div>
      {jobs.length > 0 && (
        <section className="workspace-surface active-jobs">
          <div className="section-heading"><div><h2>{t("pipeline.currentTitle")}</h2><p>{t("pipeline.currentDescription")}</p></div></div>
          {jobs.slice(0, 8).map((job) => {
            const expanded = expandedJob === job.id;
            const detail = job.error || job.result?.hpath || (job.status === "awaiting_review" ? t("pipeline.awaitingReviewHelp") : t("pipeline.working"));
            return (
              <article className={`job-card${expanded ? " job-card-expanded" : ""}`} key={job.id}>
                <button className="run-row job-row" type="button" aria-expanded={expanded} onClick={() => setExpandedJob(expanded ? null : job.id)}>
                  <span className="run-state-icon">{job.status === "failed" ? <WarningCircle size={21} /> : job.status === "succeeded" || job.status === "awaiting_review" ? <Check size={20} /> : <Circle size={18} />}</span>
                  <span><strong>{job.url}</strong><small>{detail}</small></span>
                  <span className="job-row-tail"><span className={`job-status job-${job.status}`}>{t(`status.${job.status}`)}</span>{expanded ? <CaretUp size={16} /> : <CaretDown size={16} />}</span>
                </button>
                {expanded && (
                  <div className="job-observability">
                    <div className="job-events" aria-label={t("pipeline.eventLog")}>
                      {job.events.map((event) => (
                        <div className={`job-event job-event-${event.level}`} key={event.id}>
                          <time>{new Date(event.at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}</time>
                          <span><strong>{t(event.message)}</strong>{event.details && <small>{event.details}</small>}</span>
                        </div>
                      ))}
                    </div>
                    {job.reviewPreview && (
                      <div className="review-stream"><div><TerminalWindow size={17} /><strong>{t("pipeline.reviewStream")}</strong></div><pre>{job.reviewPreview}</pre></div>
                    )}
                    {job.articleId && <Link className="button-secondary job-review-link" to={`/articles/${encodeURIComponent(job.articleId)}`}>{job.status === "awaiting_review" ? t("pipeline.reviewArticle") : t("pipeline.openArticle")}</Link>}
                  </div>
                )}
              </article>
            );
          })}
        </section>
      )}
      <section className="workspace-surface run-list">
        <div className="section-heading"><div><h2>{t("pipeline.articleStateTitle")}</h2><p>{t("pipeline.articleStateDescription")}</p></div></div>
        {query.isLoading && <LoadingPanel />}
        {query.isError && <ErrorPanel message={(query.error as Error).message} />}
        {articles.map((article) => (
          <Link to={`/articles/${encodeURIComponent(article.id)}`} className="run-row" key={article.id}>
            <span className="run-state-icon">{article.status === "failed" ? <WarningCircle size={21} /> : article.status === "captured" ? <Circle size={18} /> : <Check size={20} />}</span>
            <span><strong>{article.title}</strong><small>{localizedPlatformLabel(article.platform, article.platformLabel, t)}</small></span>
            <StatusBadge status={article.status} />
          </Link>
        ))}
        {!query.isLoading && !articles.length && <div className="empty-state compact"><h3>{t("pipeline.emptyTitle")}</h3><p>{t("pipeline.emptyDescription")}</p></div>}
      </section>
    </div>
  );
}
