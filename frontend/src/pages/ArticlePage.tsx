import { ArrowCounterClockwise, ArrowLeft, ArrowSquareOut, CaretDown, CheckCircle, Eye, EyeSlash, FileText, FloppyDisk, FolderOpen, Image, MagicWand, Notebook, PencilSimple, SidebarSimple, SpinnerGap, Trash, UploadSimple, WarningCircle, X } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useBeforeUnload, useBlocker, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ArticleOutline } from "../components/ArticleOutline";
import { InlineSelect } from "../components/InlineSelect";
import { MarkdownEditor } from "../components/MarkdownEditor";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import { StatusBadge } from "../components/StatusBadge";
import { localizedPlatformLabel } from "../localization";
import type { CollectionNode, OutputLanguage } from "../types";

function collectionOptions(nodes: CollectionNode[], path: string[] = []): Array<{ value: string; label: string; description?: string }> {
  return nodes.flatMap((node) => {
    const currentPath = [...path, node.name];
    return [
      {
        value: node.id,
        label: currentPath.join(" / "),
        description: node.description
      },
      ...collectionOptions(node.children, currentPath)
    ];
  });
}

async function digestText(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function ArticlePage() {
  const { t, i18n } = useTranslation();
  const { articleId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["article", articleId, i18n.resolvedLanguage], queryFn: () => api.getArticle(articleId), enabled: Boolean(articleId) });
  const collectionQuery = useQuery({ queryKey: ["collections", i18n.resolvedLanguage], queryFn: api.getCollections });
  const pipelineSettingsQuery = useQuery({ queryKey: ["pipeline-settings", i18n.resolvedLanguage], queryFn: api.getPipelineSettings });
  const [draft, setDraft] = useState("");
  const [readOnly, setReadOnly] = useState(true);
  const [uploadJobId, setUploadJobId] = useState<string | null>(null);
  const [reviewJobId, setReviewJobId] = useState<string | null>(null);
  const [reviewPerspective, setReviewPerspective] = useState("");
  const [reviewLanguage, setReviewLanguage] = useState<OutputLanguage>("follow_ui");
  const [collectionId, setCollectionId] = useState("");
  const [sourceExpanded, setSourceExpanded] = useState(false);
  const [inspectionOpen, setInspectionOpen] = useState(true);
  const [metadataAuthor, setMetadataAuthor] = useState("");
  const [metadataPublishedAt, setMetadataPublishedAt] = useState("");
  const [pendingImageAction, setPendingImageAction] = useState<{ name: string; state: "active" | "removed" } | null>(null);
  const [pendingImageStates, setPendingImageStates] = useState<Record<string, "active" | "removed">>({});
  const [showRemovedImages, setShowRemovedImages] = useState(true);
  const [previewAsset, setPreviewAsset] = useState<{ name: string; url: string; removed: boolean; reason?: string } | null>(null);
  const [reflectionOpen, setReflectionOpen] = useState(false);
  const [reflectionDraft, setReflectionDraft] = useState("");
  const [reflectionSavedSnapshot, setReflectionSavedSnapshot] = useState("");
  const [reflectionDraftDigest, setReflectionDraftDigest] = useState("");
  const [polishJobId, setPolishJobId] = useState<string | null>(null);

  useEffect(() => {
    document.body.classList.add("article-route-active");
    window.scrollTo({ top: 0, left: 0 });
    return () => document.body.classList.remove("article-route-active");
  }, []);

  useEffect(() => {
    if (!query.data) return;
    setDraft(query.data.editableMarkdown);
    setUploadJobId(query.data.activeUpload?.id ?? null);
    setReviewJobId(query.data.activeReview?.id ?? null);
    setCollectionId(query.data.collection?.collection_id ?? "");
    setMetadataAuthor(query.data.metadata.author.origin === "missing" ? "" : query.data.metadata.author.value);
    setMetadataPublishedAt(query.data.metadata.publishedAt.origin === "missing" ? "" : query.data.metadata.publishedAt.value);
    if (!reflectionOpen) {
      setPolishJobId(query.data.activePolish?.id ?? null);
      setReflectionDraft(query.data.reflection.markdown);
      setReflectionSavedSnapshot(query.data.reflection.markdown);
    }
  }, [query.data, reflectionOpen]);
  useEffect(() => {
    setReadOnly(true);
    setSourceExpanded(false);
    setPreviewAsset(null);
    setPendingImageAction(null);
    setPendingImageStates({});
    setShowRemovedImages(true);
    setReflectionOpen(false);
    setReflectionDraft("");
    setReflectionSavedSnapshot("");
  }, [articleId]);
  useEffect(() => {
    let current = true;
    void digestText(reflectionDraft).then((digest) => {
      if (current) setReflectionDraftDigest(digest);
    });
    return () => { current = false; };
  }, [reflectionDraft]);
  const reflectionDirty = reflectionDraft !== reflectionSavedSnapshot;
  const closeReflectionDialog = useCallback(() => {
    if (reflectionDirty && !window.confirm(t("article.reflectionDiscardChanges"))) return;
    setReflectionOpen(false);
  }, [reflectionDirty, t]);
  useEffect(() => {
    if (!reflectionOpen) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeReflectionDialog();
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [closeReflectionDialog, reflectionOpen]);
  useEffect(() => {
    if (!previewAsset) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPreviewAsset(null);
    };
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [previewAsset]);
  useEffect(() => {
    if (!pipelineSettingsQuery.data) return;
    if (!reviewPerspective) setReviewPerspective(pipelineSettingsQuery.data.activePerspective);
    setReviewLanguage((current) => current === "follow_ui" ? pipelineSettingsQuery.data.outputLanguage : current);
  }, [pipelineSettingsQuery.data, reviewPerspective]);
  const dirty = Boolean(query.data && (
    draft !== query.data.editableMarkdown
    || Object.keys(pendingImageStates).length > 0
  ));
  const blocker = useBlocker(({ currentLocation, nextLocation }) =>
    dirty && (
      currentLocation.pathname !== nextLocation.pathname
      || currentLocation.search !== nextLocation.search
      || currentLocation.hash !== nextLocation.hash
    )
  );
  useBeforeUnload(useCallback((event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  }, [dirty]));

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
  const polishJobQuery = useQuery({
    queryKey: ["polish-job", polishJobId],
    queryFn: () => api.getPolishJob(polishJobId!),
    enabled: Boolean(polishJobId),
    refetchInterval: (state) => state.state.data && ["succeeded", "failed"].includes(state.state.data.status) ? false : 700
  });
  useEffect(() => {
    if (!polishJobQuery.data || !["succeeded", "failed"].includes(polishJobQuery.data.status)) return;
    void queryClient.invalidateQueries({ queryKey: ["article", articleId] });
  }, [articleId, polishJobQuery.data, queryClient]);
  useEffect(() => {
    if (reviewJobQuery.data?.status !== "succeeded") return;
    void queryClient.invalidateQueries({ queryKey: ["article", articleId] });
    void queryClient.invalidateQueries({ queryKey: ["articles"] });
    void queryClient.invalidateQueries({ queryKey: ["collections"] });
  }, [articleId, queryClient, reviewJobQuery.data?.status]);

  const saveMutation = useMutation({
    mutationFn: () => api.saveReviewedMarkdown(articleId, draft, pendingImageStates),
    onSuccess: async () => {
      setPendingImageStates({});
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
      await queryClient.invalidateQueries({ queryKey: ["articles"] });
    }
  });
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (dirty) await api.saveReviewedMarkdown(articleId, draft, pendingImageStates);
      return api.uploadArticle(articleId);
    },
    onSuccess: async (job) => {
      setPendingImageStates({});
      setUploadJobId(job.id);
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
    }
  });
  const reviewMutation = useMutation({
    mutationFn: async () => {
      if (dirty) await api.saveReviewedMarkdown(articleId, draft, pendingImageStates);
      return api.reviewArticle(articleId, reviewPerspective, reviewLanguage);
    },
    onSuccess: async (job) => {
      setPendingImageStates({});
      setReviewJobId(job.id);
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
    }
  });
  const saveReflectionMutation = useMutation({
    mutationFn: (payload: { markdown?: string; uploadEnabled?: boolean }) => api.saveReflection(articleId, payload),
    onSuccess: async (result, variables) => {
      if (variables.markdown !== undefined) setReflectionSavedSnapshot(result.markdown);
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
    }
  });
  const polishMutation = useMutation({
    mutationFn: () => api.polishArticle(articleId, reflectionDraft),
    onSuccess: (job) => setPolishJobId(job.id)
  });
  const collectionMutation = useMutation({
    mutationFn: () => api.updateArticleCollection(articleId, collectionId || undefined),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["article", articleId] });
      await queryClient.invalidateQueries({ queryKey: ["articles"] });
      await queryClient.invalidateQueries({ queryKey: ["collections"] });
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

  const availableCollections = useMemo(
    () => collectionOptions(collectionQuery.data?.collections ?? []),
    [collectionQuery.data]
  );

  if (query.isLoading) return <div className="page"><LoadingPanel label={t("common.loadingArticle")} /></div>;
  if (query.isError || !query.data) return <div className="page"><ErrorPanel message={(query.error as Error)?.message ?? t("common.articleNotFound")} /></div>;

  const article = query.data;
  const reflection = article.reflection;
  const platformLabel = localizedPlatformLabel(article.platform, article.platformLabel, t);
  const uploadJob = uploadJobQuery.data ?? article.activeUpload;
  const uploading = Boolean(uploadMutation.isPending || (uploadJobId && (!uploadJob || ["queued", "running"].includes(uploadJob.status))));
  const reviewJob = reviewJobQuery.data ?? article.activeReview;
  const reviewing = reviewMutation.isPending || Boolean(reviewJobId && (!reviewJob || ["queued", "running"].includes(reviewJob.status)));
  const polishJob = polishJobQuery.data ?? article.activePolish;
  const polishing = polishMutation.isPending || Boolean(polishJobId && (!polishJob || ["queued", "running"].includes(polishJob.status)));
  const polishStale = Boolean(
    polishJob?.status === "succeeded"
    && reflectionDraftDigest
    && polishJob.inputDigest !== reflectionDraftDigest
  );
  const imageInventory = [
    ...article.assets.map((asset) => ({ ...asset, originalState: "active" as const, reason: "", source: "manual" as const })),
    ...article.removedAssets.map((asset) => ({ ...asset, originalState: "removed" as const }))
  ];
  const effectiveActiveAssets = imageInventory.filter(
    (asset) => (pendingImageStates[asset.name] ?? asset.originalState) === "active"
  );
  const effectiveRemovedAssets = imageInventory.filter(
    (asset) => (pendingImageStates[asset.name] ?? asset.originalState) === "removed"
  );
  const effectiveRemovedAssetNames = effectiveRemovedAssets.map((asset) => asset.name);
  const openReflectionDialog = () => {
    setReflectionDraft(reflection.markdown);
    setReflectionSavedSnapshot(reflection.markdown);
    setPolishJobId((current) => current ?? article.activePolish?.id ?? null);
    setReflectionOpen(true);
  };
  const applyPolishedReflection = async () => {
    if (!polishJob?.polishPreview || polishStale) return;
    const currentDigest = await digestText(reflectionDraft);
    if (currentDigest !== polishJob.inputDigest) return;
    const polished = polishJob.polishPreview;
    setReflectionDraft(polished);
    setPolishJobId(null);
    saveReflectionMutation.mutate({ markdown: polished });
  };
  const stageImageChange = (name: string, state: "active" | "removed") => {
    const originalState = imageInventory.find((asset) => asset.name === name)?.originalState;
    setPendingImageStates((current) => {
      const next = { ...current };
      if (originalState === state) delete next[name];
      else next[name] = state;
      return next;
    });
    setPendingImageAction(null);
  };
  const cancelLeaving = () => {
    if (blocker.state === "blocked") blocker.reset();
  };
  const discardAndLeave = () => {
    if (blocker.state === "blocked") blocker.proceed();
  };
  const saveAndLeave = () => {
    if (blocker.state !== "blocked") return;
    const proceed = blocker.proceed;
    saveMutation.mutate(undefined, { onSuccess: () => proceed() });
  };

  return (
    <div className="page article-page">
      <header className="article-toolbar">
        <div className="article-toolbar-main">
          <button className="article-back-button" type="button" onClick={() => navigate(-1)} aria-label={t("common.back")}>
            <ArrowLeft size={18} />
          </button>
          <div className="article-toolbar-identity">
            <strong>{article.title}</strong>
            <span className={`article-save-state${dirty ? " dirty" : ""}${saveMutation.isError ? " error" : ""}`}>
              {saveMutation.isPending
                ? <SpinnerGap className="spin" size={12} />
                : !dirty && !saveMutation.isError
                  ? <CheckCircle size={12} weight="fill" />
                  : null}
              {saveMutation.isPending
                ? t("article.saving")
                : saveMutation.isError
                  ? t("article.saveFailed")
                  : dirty
                    ? t("article.unsaved")
                    : t("article.saved")}
            </span>
          </div>
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
            {!readOnly && <button className="button-secondary article-save-button" type="button" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending || !dirty}>
              {saveMutation.isPending ? <SpinnerGap className="spin" size={17} /> : <FloppyDisk size={17} />}{t("article.saveDraft")}
            </button>}
          </div>
        </div>
        <nav className="article-breadcrumb" aria-label={t("article.breadcrumb")}>
          <button type="button" className="article-breadcrumb-root" onClick={() => navigate("/")}>{t("knowledge.title")}</button>
          {(article.collection?.collection_path ?? []).map((item) => (
            <button type="button" onClick={() => navigate(`/collections/${encodeURIComponent(item.id)}`)} key={item.id}>{item.name}</button>
          ))}
          <span>{article.title}</span>
        </nav>
      </header>
      <div className={`article-layout${inspectionOpen ? "" : " inspection-collapsed"}`}>
        <ArticleOutline markdown={draft} />
        <article className={`reader-surface editor-surface${readOnly ? " has-external-title" : ""}`}>
          {readOnly && (
            <header className="article-title-block">
              <h1>{article.title}</h1>
              {!!(article.collection?.collection_path ?? []).length && <div className="article-collection-chips">
                {(article.collection?.collection_path ?? []).map((item) => (
                  <button type="button" onClick={() => navigate(`/collections/${encodeURIComponent(item.id)}`)} key={item.id}>
                    <FolderOpen size={13} />
                    {item.name}
                  </button>
                ))}
              </div>}
            </header>
          )}
          <MarkdownEditor
            articleId={articleId}
            value={draft}
            readOnly={readOnly}
            removedAssetNames={effectiveRemovedAssetNames}
            showRemovedImages={showRemovedImages}
            onDeleteImage={(name) => setPendingImageAction({ name, state: "removed" })}
            onRestoreImage={(name) => setPendingImageAction({ name, state: "active" })}
            onChange={setDraft}
          />
          <section className="reflection-section" aria-label={t("article.reflectionTitle")}>
            <header className="reflection-section-header">
              <div>
                <span>{t("article.reflectionEyebrow")}</span>
                <h2>{t("article.reflectionTitle")}</h2>
              </div>
              <button className="button-secondary" type="button" onClick={openReflectionDialog}>
                <PencilSimple size={15} />
                {reflection.exists ? t("article.reflectionEdit") : t("article.reflectionWrite")}
              </button>
            </header>
            {reflection.exists
              ? <div className="reflection-section-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{reflection.markdown}</ReactMarkdown></div>
              : <p className="reflection-empty-hint">{t("article.reflectionEmptyHint")}</p>}
          </section>
          {(saveMutation.isError || uploadMutation.isError) && <p className="article-action-error" role="alert">{((saveMutation.error || uploadMutation.error) as Error).message}</p>}
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
            <div className="inspection-title"><FolderOpen size={19} /><h2>{t("article.collection")}</h2></div>
            <div className="collection-controls">
              <InlineSelect
                value={collectionId || "__root"}
                ariaLabel={t("article.collection")}
                onChange={(value) => setCollectionId(value === "__root" ? "" : value)}
                disabled={readOnly || collectionQuery.isLoading}
                options={[
                  { value: "__root", label: t("knowledge.unfiled"), description: t("article.collectionRootHelp") },
                  ...availableCollections
                ]}
              />
              {article.collection?.source === "ai" && <p className="rail-note">{t("article.aiCollectionConfidence", { confidence: Math.round(article.collection.confidence * 100) })}</p>}
              <button className="button-secondary" type="button" onClick={() => collectionMutation.mutate()} disabled={readOnly || collectionMutation.isPending}>{t("article.moveCollection")}</button>
              {collectionMutation.isError && <p className="article-action-error" role="alert">{(collectionMutation.error as Error).message}</p>}
            </div>
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

          <section className="inspection-section reflection-rail-section">
            <div className="inspection-title"><Notebook size={19} /><h2>{t("article.reflectionTitle")}</h2></div>
            <p className="rail-note">{t("article.reflectionRailHelp")}</p>
            <p className="operation-counts">{t("article.reflectionPolishCount", { count: article.operationSummary.reflectCount })}</p>
            <label className="reflection-upload-toggle">
              <input
                type="checkbox"
                checked={reflection.uploadEnabled}
                disabled={saveReflectionMutation.isPending}
                onChange={(event) => saveReflectionMutation.mutate({ uploadEnabled: event.target.checked })}
              />
              <span>{t("article.reflectionUploadToggle")}</span>
            </label>
            <button className="button-primary" type="button" onClick={openReflectionDialog}>
              <PencilSimple size={17} />
              {reflection.exists ? t("article.reflectionEdit") : t("article.reflectionWrite")}
            </button>
            {saveReflectionMutation.isError && <p className="article-action-error" role="alert">{(saveReflectionMutation.error as Error).message}</p>}
          </section>

          <section className="inspection-section">
            <div className="inspection-title">
              <Image size={19} />
              <h2>{t("article.assets")}</h2>
              {effectiveRemovedAssets.length > 0 && (
                <button
                  className="asset-visibility-toggle"
                  type="button"
                  aria-pressed={!showRemovedImages}
                  aria-label={showRemovedImages ? t("article.hideRemovedImages") : t("article.showRemovedImages")}
                  title={showRemovedImages ? t("article.hideRemovedImages") : t("article.showRemovedImages")}
                  onClick={() => setShowRemovedImages((visible) => !visible)}
                >
                  {showRemovedImages ? <EyeSlash size={15} /> : <Eye size={15} />}
                </button>
              )}
              <span>{effectiveActiveAssets.length}</span>
            </div>
            {effectiveActiveAssets.length ? (
              <div className="asset-grid">
                {effectiveActiveAssets.map((asset) => (
                  <button
                    type="button"
                    aria-label={t("article.previewImageNamed", { name: asset.name })}
                    onClick={() => setPreviewAsset({ ...asset, removed: false })}
                    key={asset.name}
                  >
                    <img src={asset.url} alt="" loading="lazy" />
                  </button>
                ))}
              </div>
            ) : <p className="rail-note">{t("article.noAssets")}</p>}
            {showRemovedImages && effectiveRemovedAssets.length > 0 && (
              <div className="removed-assets">
                <h3>{t("article.removedAssets")}</h3>
                <div className="asset-grid">
                  {effectiveRemovedAssets.map((asset) => {
                    const pending = pendingImageStates[asset.name] === "removed";
                    const reason = pending
                      ? t("article.pendingImageRemoval")
                      : asset.reason || t(`article.imageRemovalSource.${asset.source}`);
                    return (
                      <button
                        type="button"
                        aria-label={t("article.previewImageNamed", { name: asset.name })}
                        title={reason}
                        onClick={() => setPreviewAsset({ name: asset.name, url: asset.url, removed: true, reason })}
                        key={asset.name}
                      >
                        <img src={asset.url} alt="" loading="lazy" />
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
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
      {reflectionOpen && createPortal(
        <div className="dialog-layer reflection-dialog-layer" role="presentation" onMouseDown={closeReflectionDialog}>
          <section
            className="reflection-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reflection-dialog-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="reflection-dialog-header">
              <div>
                <span>{t("article.reflectionEyebrow")}</span>
                <h2 id="reflection-dialog-title">{t("article.reflectionDialogTitle")}</h2>
              </div>
              <button type="button" aria-label={t("article.reflectionClose")} onClick={closeReflectionDialog}><X size={20} /></button>
            </header>
            <textarea
              autoFocus
              className="reflection-dialog-input"
              value={reflectionDraft}
              onChange={(event) => setReflectionDraft(event.target.value)}
              placeholder={t("article.reflectionPlaceholder")}
            />
            {(polishing || polishJob?.status === "succeeded") && (
              <div className="upload-progress" aria-live="polite">
                <div><span>{t(`article.polishStages.${polishJob?.stage ?? "queued"}`)}</span><strong>{polishJob?.progress ?? 0}%</strong></div>
                <progress max="100" value={polishJob?.progress ?? 0} />
              </div>
            )}
            {polishJob?.status === "succeeded" && (
              <div className={`reflection-preview${polishStale ? " stale" : ""}`}>
                <header>
                  <h3>{t("article.reflectionPreview")}</h3>
                  <span>{[polishJob.provider, polishJob.model].filter(Boolean).join(" · ")}</span>
                </header>
                {polishStale && <p className="reflection-stale-warning" role="alert">{t("article.reflectionPreviewStale")}</p>}
                <div className="reflection-preview-body"><ReactMarkdown remarkPlugins={[remarkGfm]}>{polishJob.polishPreview}</ReactMarkdown></div>
                <div className="reflection-preview-actions">
                  <button className="button-secondary" type="button" onClick={() => setPolishJobId(null)}>{t("article.reflectionDiscardPreview")}</button>
                  <button className="button-primary" type="button" disabled={polishStale} onClick={applyPolishedReflection}>{t("article.reflectionApply")}</button>
                </div>
              </div>
            )}
            {(polishMutation.isError || polishJob?.status === "failed" || saveReflectionMutation.isError) && (
              <p className="article-action-error" role="alert">{(polishMutation.error as Error)?.message || polishJob?.error || (saveReflectionMutation.error as Error)?.message}</p>
            )}
            <footer className="reflection-dialog-footer">
              <button className="button-secondary" type="button" onClick={closeReflectionDialog}>{t("common.cancel")}</button>
              <button className="button-secondary" type="button" onClick={() => polishMutation.mutate()} disabled={polishing || !reflectionDraft.trim()}>
                <MagicWand size={16} />{polishing ? t("article.reflectionPolishing") : t("article.reflectionPolish")}
              </button>
              <button className="button-primary" type="button" onClick={() => saveReflectionMutation.mutate({ markdown: reflectionDraft })} disabled={saveReflectionMutation.isPending || !reflectionDirty}>
                {saveReflectionMutation.isPending ? <SpinnerGap className="spin" size={16} /> : <FloppyDisk size={16} />}
                {t("article.reflectionSave")}
              </button>
            </footer>
          </section>
        </div>,
        document.body
      )}
      {pendingImageAction && createPortal(
        <div className="article-confirm-backdrop modal-root-layer" role="presentation" onMouseDown={() => setPendingImageAction(null)}>
          <section className="article-confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="image-confirm-title" aria-describedby="image-confirm-description" onMouseDown={(event) => event.stopPropagation()}>
            <span className={`article-confirm-icon article-confirm-icon-${pendingImageAction.state}`}><Image size={22} /></span>
            <div>
              <h2 id="image-confirm-title">{pendingImageAction.state === "removed" ? t("article.confirmDeleteImageTitle") : t("article.confirmRestoreImageTitle")}</h2>
              <p id="image-confirm-description">{pendingImageAction.state === "removed" ? t("article.confirmDeleteImageDescription", { name: pendingImageAction.name }) : t("article.confirmRestoreImageDescription", { name: pendingImageAction.name })}</p>
            </div>
            <div className="article-confirm-actions">
              <button type="button" className="button-secondary" onClick={() => setPendingImageAction(null)}>{t("common.cancel")}</button>
              <button type="button" className={pendingImageAction.state === "removed" ? "button-danger" : "button-primary"} onClick={() => stageImageChange(pendingImageAction.name, pendingImageAction.state)}>
                {t("common.confirm")}
              </button>
            </div>
          </section>
        </div>,
        document.body
      )}
      {blocker.state === "blocked" && createPortal(
        <div className="article-confirm-backdrop modal-root-layer" role="presentation" onMouseDown={cancelLeaving}>
          <section
            className="article-confirm-dialog article-leave-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="article-leave-title"
            aria-describedby="article-leave-description"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <span className="article-confirm-icon article-leave-icon"><WarningCircle size={23} /></span>
            <div>
              <h2 id="article-leave-title">{t("article.unsavedLeaveTitle")}</h2>
              <p id="article-leave-description">{t("article.unsavedLeaveDescription")}</p>
              {saveMutation.isError && <p className="article-action-error" role="alert">{(saveMutation.error as Error).message}</p>}
            </div>
            <div className="article-confirm-actions article-leave-actions">
              <button type="button" className="button-secondary" disabled={saveMutation.isPending} onClick={cancelLeaving}>
                {t("article.continueEditing")}
              </button>
              <button type="button" className="button-secondary article-discard-button" disabled={saveMutation.isPending} onClick={discardAndLeave}>
                {t("article.discardAndLeave")}
              </button>
              <button type="button" className="button-primary" disabled={saveMutation.isPending} onClick={saveAndLeave}>
                {saveMutation.isPending ? <SpinnerGap className="spin" size={16} /> : <FloppyDisk size={16} />}
                {t("article.saveAndLeave")}
              </button>
            </div>
          </section>
        </div>,
        document.body
      )}
      {previewAsset && createPortal(
        <div className="asset-lightbox-backdrop" role="presentation" onMouseDown={() => setPreviewAsset(null)}>
          <section
            className="asset-lightbox"
            role="dialog"
            aria-modal="true"
            aria-labelledby="asset-lightbox-title"
            aria-describedby={previewAsset.reason ? "asset-lightbox-reason" : undefined}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="asset-lightbox-header">
              <div>
                <span>{previewAsset.removed ? t("article.removedImagePreview") : t("article.imagePreview")}</span>
                <h2 id="asset-lightbox-title">{previewAsset.name}</h2>
              </div>
              <button type="button" autoFocus aria-label={t("article.closeImagePreview")} onClick={() => setPreviewAsset(null)}>
                <X size={20} />
              </button>
            </header>
            <div className="asset-lightbox-stage">
              <img src={previewAsset.url} alt={previewAsset.name} />
            </div>
            <footer className="asset-lightbox-footer">
              {previewAsset.reason
                ? <p id="asset-lightbox-reason" className="asset-lightbox-reason">{previewAsset.reason}</p>
                : <span />}
              <button
                type="button"
                className={previewAsset.removed ? "button-secondary" : "button-danger"}
                onClick={() => {
                  setReadOnly(false);
                  setPreviewAsset(null);
                  setPendingImageAction({
                    name: previewAsset.name,
                    state: previewAsset.removed ? "active" : "removed"
                  });
                }}
              >
                {previewAsset.removed ? <ArrowCounterClockwise size={17} /> : <Trash size={17} />}
                {previewAsset.removed ? t("article.restoreImage") : t("article.deleteImage")}
              </button>
            </footer>
          </section>
        </div>,
        document.body
      )}
    </div>
  );
}
