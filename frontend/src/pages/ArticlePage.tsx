import { ArrowSquareOut, CaretDown, Eye, FileText, FloppyDisk, Image, MagicWand, PencilSimple, SidebarSimple, SpinnerGap, Tag, UploadSimple } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { api } from "../api";
import { ArticleOutline } from "../components/ArticleOutline";
import { InlineSelect } from "../components/InlineSelect";
import { MarkdownEditor } from "../components/MarkdownEditor";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import { StatusBadge } from "../components/StatusBadge";
import { localizedPlatformLabel } from "../localization";
import type { OutputLanguage } from "../types";

export function ArticlePage() {
  const { t, i18n } = useTranslation();
  const { articleId = "" } = useParams();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["article", articleId, i18n.resolvedLanguage], queryFn: () => api.getArticle(articleId), enabled: Boolean(articleId) });
  const taxonomyQuery = useQuery({ queryKey: ["taxonomy", i18n.resolvedLanguage], queryFn: api.getTaxonomy });
  const pipelineSettingsQuery = useQuery({ queryKey: ["pipeline-settings", i18n.resolvedLanguage], queryFn: api.getPipelineSettings });
  const [draft, setDraft] = useState("");
  const [dirty, setDirty] = useState(false);
  const [readOnly, setReadOnly] = useState(true);
  const [uploadJobId, setUploadJobId] = useState<string | null>(null);
  const [reviewJobId, setReviewJobId] = useState<string | null>(null);
  const [reviewPerspective, setReviewPerspective] = useState("");
  const [reviewLanguage, setReviewLanguage] = useState<OutputLanguage>("follow_ui");
  const [tagName, setTagName] = useState("");
  const [subtagName, setSubtagName] = useState("");
  const [sourceExpanded, setSourceExpanded] = useState(false);
  const [inspectionOpen, setInspectionOpen] = useState(true);
  const [metadataAuthor, setMetadataAuthor] = useState("");
  const [metadataPublishedAt, setMetadataPublishedAt] = useState("");
  const [pendingImageAction, setPendingImageAction] = useState<{ name: string; state: "active" | "removed" } | null>(null);

  useEffect(() => {
    document.body.classList.add("article-route-active");
    window.scrollTo({ top: 0, left: 0 });
    return () => document.body.classList.remove("article-route-active");
  }, []);

  useEffect(() => {
    if (!query.data) return;
    setDraft(query.data.editableMarkdown);
    setDirty(false);
    setUploadJobId(query.data.activeUpload?.id ?? null);
    setReviewJobId(query.data.activeReview?.id ?? null);
    setTagName(query.data.classification?.tag_name ?? "");
    setSubtagName(query.data.classification?.subtag_name ?? "");
    setMetadataAuthor(query.data.metadata.author.origin === "missing" ? "" : query.data.metadata.author.value);
    setMetadataPublishedAt(query.data.metadata.publishedAt.origin === "missing" ? "" : query.data.metadata.publishedAt.value);
  }, [query.data]);
  useEffect(() => {
    if (!tagName && taxonomyQuery.data?.tags[0]) setTagName(taxonomyQuery.data.tags[0].name);
  }, [tagName, taxonomyQuery.data]);
  useEffect(() => {
    if (!pipelineSettingsQuery.data) return;
    if (!reviewPerspective) setReviewPerspective(pipelineSettingsQuery.data.activePerspective);
    setReviewLanguage((current) => current === "follow_ui" ? pipelineSettingsQuery.data.outputLanguage : current);
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
      return api.reviewArticle(articleId, reviewPerspective, reviewLanguage);
    },
    onSuccess: (job) => { setDirty(false); setReviewJobId(job.id); }
  });
  const classificationMutation = useMutation({
    mutationFn: () => {
      if (!selectedTag) throw new Error(t("article.noClassification"));
      return api.updateArticleClassification(
        articleId,
        selectedTag.id,
        selectedTag.children.find((item) => item.name === subtagName)?.id
      );
    },
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
  const metadataMutation = useMutation({
    mutationFn: () => api.updateArticleMetadata(articleId, {
      ...(query.data?.metadata.author.editable ? { author: metadataAuthor } : {}),
      ...(query.data?.metadata.publishedAt.editable ? { publishedAt: metadataPublishedAt } : {})
    }),
    onSuccess: async () => {
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
  const reviewJob = reviewJobQuery.data ?? article.activeReview;
  const reviewing = reviewMutation.isPending || Boolean(reviewJobId && (!reviewJob || ["queued", "running"].includes(reviewJob.status)));

  return (
    <div className="page article-page">
      <header className="article-toolbar">
        <nav className="article-breadcrumb" aria-label={t("article.breadcrumb")}>
          <span className="article-breadcrumb-root">{t("nav.library")}</span>
          {article.classification?.tag_name && (
            <span>{article.classification.tag_name}</span>
          )}
          {article.classification?.subtag_name && (
            <span>{article.classification.subtag_name}</span>
          )}
        </nav>
        <div className="article-toolbar-actions">
          <StatusBadge status={article.status} />
          <button
            type="button"
            className={`inspection-rail-toggle${inspectionOpen ? " active" : ""}`}
            aria-pressed={inspectionOpen}
            aria-label={inspectionOpen ? t("article.hideInspection") : t("article.showInspection")}
            title={inspectionOpen ? t("article.hideInspection") : t("article.showInspection")}
            onClick={() => setInspectionOpen((open) => !open)}
          >
            <SidebarSimple size={18} weight={inspectionOpen ? "fill" : "regular"} />
          </button>
          <div className="editor-mode-toggle" aria-label={t("article.modeLabel")}>
            <button type="button" className={readOnly ? "active" : ""} onClick={() => setReadOnly(true)}><Eye size={17} />{t("article.readOnly")}</button>
            <button type="button" className={!readOnly ? "active" : ""} onClick={() => { setReadOnly(false); setSourceExpanded(true); }}><PencilSimple size={17} />{t("article.edit")}</button>
          </div>
          {!readOnly && <button className="button-secondary" type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
            {saveMutation.isPending ? <SpinnerGap className="spin" size={17} /> : <FloppyDisk size={17} />}{t("article.saveDraft")}
          </button>}
        </div>
      </header>
      <div className={`article-layout${inspectionOpen ? "" : " inspection-collapsed"}`}>
        <ArticleOutline markdown={draft} />
        <article className="reader-surface editor-surface">
          <MarkdownEditor
            articleId={articleId}
            value={draft}
            readOnly={readOnly}
            removedAssetNames={article.removedAssets.map((asset) => asset.name)}
            onDeleteImage={(name) => setPendingImageAction({ name, state: "removed" })}
            onRestoreImage={(name) => setPendingImageAction({ name, state: "active" })}
            onChange={(markdown) => { setDraft(markdown); setDirty(markdown !== article.editableMarkdown); }}
          />
          {(saveMutation.isError || uploadMutation.isError || imageMutation.isError) && <p className="article-action-error" role="alert">{((saveMutation.error || uploadMutation.error || imageMutation.error) as Error).message}</p>}
        </article>

        <aside className="inspection-rail" aria-hidden={!inspectionOpen}>
          <section className={`inspection-section inspection-source-section${sourceExpanded ? " inspection-source-expanded" : ""}`}>
            <button className="inspection-collapse-toggle" type="button" aria-expanded={sourceExpanded} onClick={() => setSourceExpanded((expanded) => !expanded)}>
              <span className="inspection-title"><FileText size={19} /><h2>{t("article.source")}</h2></span>
              <CaretDown className="inspection-collapse-caret" size={17} weight="bold" />
            </button>
            <div className="inspection-source-content">
              <div>
                <dl>
                  <div><dt>{t("article.platform")}</dt><dd>{platformLabel}</dd></div>
                  <div><dt>{t("article.author")}</dt><dd>
                    {!readOnly && article.metadata.author.editable
                      ? <input className="metadata-field-input" value={metadataAuthor} onChange={(event) => setMetadataAuthor(event.target.value)} placeholder={t("article.missingMetadataPlaceholder")} />
                      : article.metadata.author.value}
                    {readOnly && article.metadata.author.editable && <span className="metadata-missing-tip">{t("article.missingMetadataTip")}</span>}
                  </dd></div>
                  <div><dt>{t("article.published")}</dt><dd>
                    {!readOnly && article.metadata.publishedAt.editable
                      ? <input className="metadata-field-input" value={metadataPublishedAt} onChange={(event) => setMetadataPublishedAt(event.target.value)} placeholder={t("article.missingMetadataPlaceholder")} />
                      : article.metadata.publishedAt.value}
                    {readOnly && article.metadata.publishedAt.editable && <span className="metadata-missing-tip">{t("article.missingMetadataTip")}</span>}
                  </dd></div>
                  <div><dt>{t("article.captured")}</dt><dd>{article.metadata.capturedAt.value}</dd></div>
                  <div><dt>{t("article.type")}</dt><dd>{t(`article.types.${article.contentType}`, { defaultValue: article.contentType })}</dd></div>
                </dl>
                {(["author", "publishedAt"] as const).map((key) => article.metadata[key].origin === "ai" && article.metadata[key].evidence
                  ? <div className="metadata-evidence" key={key}>
                    <strong>{t("article.aiMetadataEvidence", { field: key === "author" ? t("article.author") : t("article.published") })}</strong>
                    <q>{article.metadata[key].evidence}</q>
                    <span>{[article.metadata[key].provider, article.metadata[key].model].filter(Boolean).join(" · ")}</span>
                  </div>
                  : null)}
                {!readOnly && (article.metadata.author.editable || article.metadata.publishedAt.editable) && <button className="button-secondary metadata-save-button" type="button" onClick={() => metadataMutation.mutate()} disabled={metadataMutation.isPending}>{t("article.saveMissingMetadata")}</button>}
                {!readOnly && !article.metadata.author.editable && !article.metadata.publishedAt.editable && <p className="rail-note">{t("article.metadataProtected")}</p>}
                {metadataMutation.isError && <p className="article-action-error" role="alert">{(metadataMutation.error as Error).message}</p>}
                <a href={article.url} target="_blank" rel="noreferrer" className="source-link">{t("article.openSource")} <ArrowSquareOut size={16} /></a>
              </div>
            </div>
          </section>

          <section className="inspection-section">
            <div className="inspection-title"><Tag size={19} /><h2>{t("article.classification")}</h2></div>
            {taxonomyQuery.data?.tags.length ? <div className="classification-controls">
              <InlineSelect value={tagName || taxonomyQuery.data.tags[0].name} ariaLabel={t("article.tag")} onChange={(value) => { setTagName(value); setSubtagName(""); }} disabled={readOnly} options={taxonomyQuery.data.tags.map((tag) => ({ value: tag.name, label: tag.name, description: tag.description }))} />
              {selectedTag?.children.length ? <InlineSelect value={subtagName || "__none"} ariaLabel={t("article.subtag")} onChange={(value) => setSubtagName(value === "__none" ? "" : value)} disabled={readOnly} options={[{ value: "__none", label: t("article.noSubtag") }, ...selectedTag.children.map((tag) => ({ value: tag.name, label: tag.name, description: tag.description }))]} /> : null}
              {article.classification?.source === "ai" && <p className="rail-note">{t("article.aiClassificationConfidence", { confidence: Math.round(article.classification.confidence * 100) })}</p>}
              <button className="button-secondary" type="button" onClick={() => classificationMutation.mutate()} disabled={readOnly || !tagName || classificationMutation.isPending}>{t("article.moveCategory")}</button>
            </div> : <p className="rail-note">{t("article.noClassification")}</p>}
          </section>

          <section className="inspection-section article-review-section">
            <div className="inspection-title"><MagicWand size={19} /><h2>{t("article.aiSecondReview")}</h2></div>
            <p className="rail-note">{t("article.aiSecondReviewHelp")}</p>
            <div className="article-review-controls">
              {pipelineSettingsQuery.data && <InlineSelect value={reviewPerspective || pipelineSettingsQuery.data.activePerspective} ariaLabel={t("pipeline.perspective")} onChange={setReviewPerspective} disabled={readOnly || reviewing} options={pipelineSettingsQuery.data.perspectives.map((item) => ({ value: item.id, label: item.label, description: item.description }))} />}
              <InlineSelect<OutputLanguage> value={reviewLanguage} ariaLabel={t("pipeline.outputLanguage")} onChange={setReviewLanguage} disabled={readOnly || reviewing} options={(["follow_ui", "source", "zh-CN", "en-US"] as const).map((value) => ({ value, label: t(`pipeline.languages.${value}`), description: t(`pipeline.languagesHelp.${value}`) }))} />
              <p className="operation-counts">{t("article.reviewCount", { count: article.operationSummary.reviewCount })} · {t("article.rereviewCount", { count: article.operationSummary.rereviewCount })}</p>
              {(reviewing || reviewJob?.status === "succeeded") && <div className="upload-progress" aria-live="polite"><div><span>{t(`article.reviewStages.${reviewJob?.stage ?? "queued"}`)}</span><strong>{reviewJob?.progress ?? 0}%</strong></div><progress max="100" value={reviewJob?.progress ?? 0} /></div>}
              {(reviewMutation.isError || reviewJob?.status === "failed") && <p className="article-action-error" role="alert">{(reviewMutation.error as Error)?.message || reviewJob?.error}</p>}
              <button className="button-primary" type="button" onClick={() => reviewMutation.mutate()} disabled={readOnly || !reviewPerspective || reviewing}><MagicWand size={17} />{reviewing ? t("article.aiReviewing") : t("article.startAiSecondReview")}</button>
            </div>
          </section>

          <section className="inspection-section">
            <div className="inspection-title"><Image size={19} /><h2>{t("article.assets")}</h2><span>{article.assets.length}</span></div>
            {article.assets.length ? <div className="asset-grid">{article.assets.map((asset) => <a href={asset.url} target="_blank" rel="noreferrer" key={asset.name}><img src={asset.url} alt={asset.name} loading="lazy" /></a>)}</div> : <p className="rail-note">{t("article.noAssets")}</p>}
            {article.removedAssets.length > 0 && <div className="removed-assets"><h3>{t("article.removedAssets")}</h3><div className="asset-grid">{article.removedAssets.map((asset) => <a href={asset.url} target="_blank" rel="noreferrer" title={asset.reason || t(`article.imageRemovalSource.${asset.source}`)} key={asset.name}><img src={asset.url} alt={asset.name} loading="lazy" /></a>)}</div></div>}
          </section>

          <section className="inspection-section upload-section">
            <h2>{t("article.destination")}</h2>
            <p>{article.hasUploaded ? t("article.uploadedBefore") : t("article.notUploaded")}</p>
            <p className="operation-counts">{t("article.uploadCount", { count: article.operationSummary.uploadCount })}</p>
            {(uploading || uploadJob?.status === "succeeded") && <div className="upload-progress" aria-live="polite"><div><span>{t(`article.uploadStages.${uploadJob?.stage ?? "queued"}`)}</span><strong>{uploadJob?.progress ?? 0}%</strong></div><progress max="100" value={uploadJob?.progress ?? 0} /></div>}
            {uploadJob?.status === "failed" && <p className="article-action-error" role="alert">{uploadJob.error}</p>}
            <button className="button-primary" type="button" onClick={() => uploadMutation.mutate()} disabled={readOnly || uploadMutation.isPending || uploading}>
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
