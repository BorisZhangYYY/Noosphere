import { ArrowLeft, ArrowSquareOut, CaretDown, CheckCircle, Eye, FileText, FloppyDisk, Image, MagicWand, PencilSimple, SpinnerGap, Tag, UploadSimple, Warning } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { InlineSelect } from "../components/InlineSelect";
import { MarkdownEditor } from "../components/MarkdownEditor";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import { StatusBadge } from "../components/StatusBadge";
import { localizedPlatformLabel } from "../localization";

export function ArticlePage() {
  const { t } = useTranslation();
  const { articleId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["article", articleId], queryFn: () => api.getArticle(articleId), enabled: Boolean(articleId) });
  const taxonomyQuery = useQuery({ queryKey: ["taxonomy"], queryFn: api.getTaxonomy });
  const pipelineSettingsQuery = useQuery({ queryKey: ["pipeline-settings"], queryFn: api.getPipelineSettings });
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [readOnly, setReadOnly] = useState(true);
  const [uploadJobId, setUploadJobId] = useState<string | null>(null);
  const [reviewJobId, setReviewJobId] = useState<string | null>(null);
  const [reviewPerspective, setReviewPerspective] = useState("");
  const [tagName, setTagName] = useState("");
  const [subtagName, setSubtagName] = useState("");
  const [sourceExpanded, setSourceExpanded] = useState(false);
  const [pendingImageAction, setPendingImageAction] = useState<{ name: string; state: "active" | "removed" } | null>(null);

  useEffect(() => {
    if (!query.data) return;
    setDraft(query.data.displayMarkdown || query.data.reviewedMarkdown || query.data.rawMarkdown);
    setDirty(false);
    setUploadJobId(query.data.activeUpload?.id ?? null);
    setTagName(query.data.classification?.tag_name ?? "");
    setSubtagName(query.data.classification?.subtag_name ?? "");
  }, [query.data]);
  useEffect(() => {
    if (!tagName && taxonomyQuery.data?.tags[0]) setTagName(taxonomyQuery.data.tags[0].name);
  }, [tagName, taxonomyQuery.data]);
  useEffect(() => {
    if (!reviewPerspective && pipelineSettingsQuery.data) setReviewPerspective(pipelineSettingsQuery.data.activePerspective);
  }, [pipelineSettingsQuery.data, reviewPerspective]);

  const uploadJobQuery = useQuery({
    queryKey: ["upload-job", uploadJobId],
    queryFn: () => api.getUploadJob(uploadJobId!),
    enabled: Boolean(uploadJobId),
    refetchInterval: (state) => state.state.data && ["succeeded", "failed"].includes(state.state.data.status) ? false : 700
  });
  useEffect(() => {
    if (uploadJobQuery.data?.status !== "succeeded") return;
    void queryClient.invalidateQueries({ queryKey: ["article", articleId] });
    void queryClient.invalidateQueries({ queryKey: ["articles"] });
  }, [articleId, queryClient, uploadJobQuery.data?.status]);
  const reviewJobQuery = useQuery({
    queryKey: ["review-job", reviewJobId],
    queryFn: () => api.getReviewJob(reviewJobId!),
    enabled: Boolean(reviewJobId),
    refetchInterval: (state) => state.state.data && ["succeeded", "failed"].includes(state.state.data.status) ? false : 700
  });
  useEffect(() => {
    if (reviewJobQuery.data?.status !== "succeeded") return;
    void queryClient.invalidateQueries({ queryKey: ["article", articleId] });
    void queryClient.invalidateQueries({ queryKey: ["articles"] });
    void queryClient.invalidateQueries({ queryKey: ["taxonomy"] });
  }, [articleId, queryClient, reviewJobQuery.data?.status]);

  const saveMutation = useMutation({
    mutationFn: () => api.saveReviewedMarkdown(articleId, draft),
    onSuccess: async () => {
      setDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
      await queryClient.invalidateQueries({ queryKey: ["articles"] });
    }
  });
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (dirty) await api.saveReviewedMarkdown(articleId, draft);
      return api.uploadArticle(articleId);
    },
    onSuccess: (job) => {
      setDirty(false);
      setUploadJobId(job.id);
    }
  });
  const reviewMutation = useMutation({
    mutationFn: async () => {
      if (dirty) await api.saveReviewedMarkdown(articleId, draft);
      return api.reviewArticle(articleId, reviewPerspective);
    },
    onSuccess: (job) => { setDirty(false); setReviewJobId(job.id); }
  });
  const classificationMutation = useMutation({
    mutationFn: () => api.updateArticleClassification(articleId, tagName, subtagName || undefined),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
      await queryClient.invalidateQueries({ queryKey: ["taxonomy"] });
    }
  });
  const imageMutation = useMutation({
    mutationFn: ({ name, state }: { name: string; state: "active" | "removed" }) => api.updateArticleImage(articleId, name, state, draft),
    onSuccess: async () => {
      setPendingImageAction(null);
      setDirty(false);
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
      await queryClient.invalidateQueries({ queryKey: ["articles"] });
    }
  });

  const selectedTag = useMemo(() => taxonomyQuery.data?.tags.find((tag) => tag.name === tagName), [tagName, taxonomyQuery.data]);

  if (query.isLoading) return <div className="page"><LoadingPanel label={t("common.loadingArticle")} /></div>;
  if (query.isError || !query.data) return <div className="page"><ErrorPanel message={(query.error as Error)?.message ?? t("common.articleNotFound")} /></div>;

  const article = query.data;
  const platformLabel = localizedPlatformLabel(article.platform, article.platformLabel, t);
  const uploadJob = uploadJobQuery.data ?? article.activeUpload;
  const uploading = Boolean(uploadMutation.isPending || (uploadJobId && (!uploadJob || ["queued", "running"].includes(uploadJob.status))));
  const reviewJob = reviewJobQuery.data;
  const reviewing = reviewMutation.isPending || Boolean(reviewJobId && (!reviewJob || ["queued", "running"].includes(reviewJob.status)));

  return (
    <div className="page article-page">
      <header className="article-toolbar">
        <Link to="/library" className="icon-text-link"><ArrowLeft size={18} />{t("nav.library")}</Link>
        <div className="article-toolbar-actions">
          <StatusBadge status={article.status} />
          <div className="editor-mode-toggle" aria-label={t("article.modeLabel")}>
            <button type="button" className={readOnly ? "active" : ""} onClick={() => setReadOnly(true)}><Eye size={17} />{t("article.readOnly")}</button>
            <button type="button" className={!readOnly ? "active" : ""} onClick={() => setReadOnly(false)}><PencilSimple size={17} />{t("article.edit")}</button>
          </div>
          {!readOnly && <button className="button-secondary" type="button" onClick={() => saveMutation.mutate()} disabled={!dirty || saveMutation.isPending}>
            {saveMutation.isPending ? <SpinnerGap className="spin" size={17} /> : <FloppyDisk size={17} />}{t("article.saveDraft")}
          </button>}
        </div>
      </header>
      <div className="article-layout">
        <article className="reader-surface editor-surface">
          <MarkdownEditor
            articleId={articleId}
            value={draft}
            readOnly={readOnly}
            removedAssetNames={article.removedAssets.map((asset) => asset.name)}
            onDeleteImage={(name) => setPendingImageAction({ name, state: "removed" })}
            onRestoreImage={(name) => setPendingImageAction({ name, state: "active" })}
            onChange={(markdown) => { setDraft(markdown); setDirty(markdown !== (article.displayMarkdown || article.reviewedMarkdown || article.rawMarkdown)); }}
          />
          {(saveMutation.isError || uploadMutation.isError || imageMutation.isError) && <p className="article-action-error" role="alert">{((saveMutation.error || uploadMutation.error || imageMutation.error) as Error).message}</p>}
        </article>

        <aside className="inspection-rail">
          <section className={`inspection-section inspection-source-section${sourceExpanded ? " inspection-source-expanded" : ""}`}>
            <button className="inspection-collapse-toggle" type="button" aria-expanded={sourceExpanded} onClick={() => setSourceExpanded((expanded) => !expanded)}>
              <span className="inspection-title"><FileText size={19} /><h2>{t("article.source")}</h2></span>
              <CaretDown className="inspection-collapse-caret" size={17} weight="bold" />
            </button>
            <div className="inspection-source-content">
              <div>
                <dl>
                  <div><dt>{t("article.platform")}</dt><dd>{platformLabel}</dd></div>
                  <div><dt>{t("article.author")}</dt><dd>{article.author || t("common.unknown")}</dd></div>
                  <div><dt>{t("article.published")}</dt><dd>{article.publishedAt || t("common.unknown")}</dd></div>
                  <div><dt>{t("article.type")}</dt><dd>{t(`article.types.${article.contentType}`, { defaultValue: article.contentType })}</dd></div>
                </dl>
                <a href={article.url} target="_blank" rel="noreferrer" className="source-link">{t("article.openSource")} <ArrowSquareOut size={16} /></a>
              </div>
            </div>
          </section>

          <section className="inspection-section">
            <div className="inspection-title"><Tag size={19} /><h2>{t("article.classification")}</h2></div>
            {taxonomyQuery.data?.tags.length ? <div className="classification-controls">
              <InlineSelect value={tagName || taxonomyQuery.data.tags[0].name} ariaLabel={t("article.tag")} onChange={(value) => { setTagName(value); setSubtagName(""); }} options={taxonomyQuery.data.tags.map((tag) => ({ value: tag.name, label: tag.name, description: tag.description }))} />
              {selectedTag?.children.length ? <InlineSelect value={subtagName || "__none"} ariaLabel={t("article.subtag")} onChange={(value) => setSubtagName(value === "__none" ? "" : value)} options={[{ value: "__none", label: t("article.noSubtag") }, ...selectedTag.children.map((tag) => ({ value: tag.name, label: tag.name, description: tag.description }))]} /> : null}
              <button className="button-secondary" type="button" onClick={() => classificationMutation.mutate()} disabled={!tagName || classificationMutation.isPending}>{t("article.moveCategory")}</button>
            </div> : <p className="rail-note">{t("article.noClassification")}</p>}
          </section>

          <section className="inspection-section article-review-section">
            <div className="inspection-title"><MagicWand size={19} /><h2>{t("article.aiSecondReview")}</h2></div>
            <p className="rail-note">{t("article.aiSecondReviewHelp")}</p>
            <div className="article-review-controls">
              {pipelineSettingsQuery.data && <InlineSelect value={reviewPerspective || pipelineSettingsQuery.data.activePerspective} ariaLabel={t("pipeline.perspective")} onChange={setReviewPerspective} disabled={reviewing} options={pipelineSettingsQuery.data.perspectives.map((item) => ({ value: item.id, label: item.label, description: item.description }))} />}
              {(reviewing || reviewJob?.status === "succeeded") && <div className="upload-progress" aria-live="polite"><div><span>{t(`article.reviewStages.${reviewJob?.stage ?? "queued"}`)}</span><strong>{reviewJob?.progress ?? 0}%</strong></div><progress max="100" value={reviewJob?.progress ?? 0} /></div>}
              {(reviewMutation.isError || reviewJob?.status === "failed") && <p className="article-action-error" role="alert">{(reviewMutation.error as Error)?.message || reviewJob?.error}</p>}
              <button className="button-primary" type="button" onClick={() => reviewMutation.mutate()} disabled={!reviewPerspective || reviewing}><MagicWand size={17} />{reviewing ? t("article.aiReviewing") : t("article.startAiSecondReview")}</button>
            </div>
          </section>

          <section className="inspection-section">
            <div className="inspection-title"><Image size={19} /><h2>{t("article.assets")}</h2><span>{article.assets.length}</span></div>
            {article.assets.length ? <div className="asset-grid">{article.assets.map((asset) => <a href={asset.url} target="_blank" rel="noreferrer" key={asset.name}><img src={asset.url} alt={asset.name} loading="lazy" /></a>)}</div> : <p className="rail-note">{t("article.noAssets")}</p>}
            {article.removedAssets.length > 0 && <div className="removed-assets"><h3>{t("article.removedAssets")}</h3><div className="asset-grid">{article.removedAssets.map((asset) => <a href={asset.url} target="_blank" rel="noreferrer" title={asset.reason || t(`article.imageRemovalSource.${asset.source}`)} key={asset.name}><img src={asset.url} alt={asset.name} loading="lazy" /></a>)}</div></div>}
          </section>

          <section className="inspection-section">
            <div className="inspection-title">{article.validationIssues.length ? <Warning size={19} /> : <CheckCircle size={19} />}<h2>{t("article.validation")}</h2></div>
            {article.validationIssues.length ? <ul className="issue-list">{article.validationIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul> : <p className="validation-ok">{t("article.noIssues")}</p>}
          </section>

          <section className="inspection-section upload-section">
            <h2>{t("article.destination")}</h2>
            <p>{article.hasUploaded ? t("article.uploadedBefore") : t("article.notUploaded")}</p>
            {(uploading || uploadJob?.status === "succeeded") && <div className="upload-progress" aria-live="polite"><div><span>{t(`article.uploadStages.${uploadJob?.stage ?? "queued"}`)}</span><strong>{uploadJob?.progress ?? 0}%</strong></div><progress max="100" value={uploadJob?.progress ?? 0} /></div>}
            {uploadJob?.status === "failed" && <p className="article-action-error" role="alert">{uploadJob.error}</p>}
            <button className="button-primary" type="button" onClick={() => uploadMutation.mutate()} disabled={uploadMutation.isPending || uploading}>
              {uploadMutation.isPending || uploading ? <SpinnerGap className="spin" size={17} /> : <UploadSimple size={17} />}
              {article.hasUploaded ? t("article.reupload") : t("article.upload")}
            </button>
            <p className="rail-note">{t("article.backgroundUploadHelp")}</p>
          </section>
        </aside>
      </div>
      {pendingImageAction && (
        <div className="article-confirm-backdrop" role="presentation" onMouseDown={() => !imageMutation.isPending && setPendingImageAction(null)}>
          <section className="article-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="image-confirm-title" aria-describedby="image-confirm-description" onMouseDown={(event) => event.stopPropagation()}>
            <span className={`article-confirm-icon article-confirm-icon-${pendingImageAction.state}`}><Image size={22} /></span>
            <div>
              <h2 id="image-confirm-title">{pendingImageAction.state === "removed" ? t("article.confirmDeleteImageTitle") : t("article.confirmRestoreImageTitle")}</h2>
              <p id="image-confirm-description">{pendingImageAction.state === "removed" ? t("article.confirmDeleteImageDescription", { name: pendingImageAction.name }) : t("article.confirmRestoreImageDescription", { name: pendingImageAction.name })}</p>
            </div>
            <div className="article-confirm-actions">
              <button type="button" className="button-secondary" onClick={() => setPendingImageAction(null)} disabled={imageMutation.isPending}>{t("common.cancel")}</button>
              <button type="button" className={pendingImageAction.state === "removed" ? "button-danger" : "button-primary"} onClick={() => imageMutation.mutate(pendingImageAction)} disabled={imageMutation.isPending}>
                {imageMutation.isPending && <SpinnerGap className="spin" size={17} />}{t("common.confirm")}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
