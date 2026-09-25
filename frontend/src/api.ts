import i18n from "./i18n";
import type { BatchJob, BatchItem, ArticleAnnotation, ArticleAnnotations, ArticleDetail, ArticleSummary, ArticleWorkspaceDetail, CaptureJob, CollectionNode, OutputLanguage, PipelineSettings, PolishJob, ReviewJob, ReviewMode, SettingsData, SettingsSecretTarget, SettingsUpdate, TrashedArticle, UploadJob } from "./types";

function locale() { return i18n.resolvedLanguage?.startsWith("zh") ? "zh-CN" : "en-US"; }
function localized(path: string) { return `${path}${path.includes("?") ? "&" : "?"}locale=${encodeURIComponent(locale())}`; }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers
    }
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({ error: response.statusText }));
    if (response.status === 401 && path !== "/api/v1/auth/login") {
      window.dispatchEvent(new Event("noosphere-auth-required"));
    }
    throw new Error(payload.error ?? `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  authStatus: () => request<{ required: boolean; authenticated: boolean }>("/api/v1/auth/status"),
  login: (password: string) => request<{ ok: boolean }>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ password }) }),
  logout: () => request<{ ok: boolean }>("/api/v1/auth/logout", { method: "POST" }),
  listBatches: () => request<{ batches: BatchJob[] }>("/api/v1/batches"),
  previewBatch: (urls: string[]) => request<{ items: BatchItem[] }>("/api/v1/batches/preview", { method: "POST", body: JSON.stringify({ urls }) }),
  createBatch: (payload: { urls: string[]; mode: string; language: string; collectionId: string }) => request<BatchJob>("/api/v1/batches", { method: "POST", body: JSON.stringify(payload) }),
  controlBatch: (id: string, action: string, itemIds?: string[]) => request<BatchJob>(`/api/v1/batches/${encodeURIComponent(id)}`, { method: "POST", body: JSON.stringify({ action, itemIds }) }),
  searchPassage: (query: string) => request<{ changed: boolean; text: string; field: string }>(`/api/v1/search/passage?${query}`),

  search: (query: string) => request<{ results: { article: ArticleSummary; matches: { field: string; digest: string; text: string; start: number; highlights: [number, number][] }[] }[]; total: number }>(localized(`/api/v1/search?${query}`)),
  rebuildSearch: () => request<{ articles: number }>("/api/v1/search/rebuild", { method: "POST" }),
  listArticles: () => request<{ articles: ArticleSummary[] }>(localized("/api/v1/articles")),
  getArticle: (articleId: string) => request<ArticleWorkspaceDetail>(localized(`/api/v1/articles/${encodeURIComponent(articleId)}?content=editable`)),
  retryMirror: (articleId: string) => request<ArticleDetail["mirrorStatus"]>(`/api/v1/articles/${encodeURIComponent(articleId)}/mirror/retry`, { method: "POST" }),
  listCaptureJobs: () => request<{ jobs: CaptureJob[] }>("/api/v1/captures"),
  retryCaptureJob: (jobId: string) => request<CaptureJob>(`/api/v1/captures/${encodeURIComponent(jobId)}/retry`, { method: "POST" }),
  createCapture: ({ url, reviewMode, perspective, outputLanguage }: { url: string; reviewMode: ReviewMode; perspective: string; outputLanguage: OutputLanguage }) => request<CaptureJob>(localized("/api/v1/captures"), {
    method: "POST",
    body: JSON.stringify({ url, reviewMode, perspective, outputLanguage })
  }),
  trashArticles: (articleIds: string[]) => request<{ articles: TrashedArticle[] }>("/api/v1/articles/batch-delete", {
    method: "POST",
    body: JSON.stringify({ articleIds })
  }),
  listTrashedArticles: () => request<{ articles: TrashedArticle[] }>("/api/v1/trash/articles"),
  restoreTrashedArticles: (articleIds: string[]) => request<{ articles: TrashedArticle[] }>("/api/v1/trash/articles/batch", {
    method: "POST",
    body: JSON.stringify({ articleIds, action: "restore" })
  }),
  permanentlyDeleteTrashedArticles: (articleIds: string[]) => request<{ deletedArticleIds: string[] }>("/api/v1/trash/articles/batch", {
    method: "POST",
    body: JSON.stringify({ articleIds, action: "delete" })
  }),
  saveReviewedMarkdown: (
    articleId: string,
    reviewedMarkdown: string,
    imageStates: Record<string, "active" | "removed"> = {},
    expectedRevision?: string
  ) =>
    request<{ ok: boolean; image_states: Record<string, "active" | "removed">; revision: string; editableMarkdown: string }>(`/api/v1/articles/${encodeURIComponent(articleId)}`, {
      method: "PATCH",
      body: JSON.stringify({ reviewedMarkdown, imageStates, expectedRevision })
    }),
  updateArticleMetadata: (articleId: string, updates: { author?: string; publishedAt?: string }) =>
    request<{ ok: boolean; metadata: ArticleDetail["metadata"] }>(`/api/v1/articles/${encodeURIComponent(articleId)}/metadata`, {
      method: "PATCH",
      body: JSON.stringify(updates)
    }),
  updateArticleImage: (articleId: string, assetName: string, state: "active" | "removed", reviewedMarkdown: string, expectedRevision: string) =>
    request<{ ok: boolean; name: string; state: "active" | "removed" }>(`/api/v1/articles/${encodeURIComponent(articleId)}/images/${encodeURIComponent(assetName)}`, {
      method: "PATCH",
      body: JSON.stringify({ state, reviewedMarkdown, expectedRevision })
    }),
  uploadArticle: (articleId: string) =>
    request<UploadJob>(`/api/v1/articles/${encodeURIComponent(articleId)}/upload`, {
      method: "POST",
      body: JSON.stringify({ target: "siyuan" })
    }),
  getUploadJob: (jobId: string) => request<UploadJob>(`/api/v1/uploads/${encodeURIComponent(jobId)}`),
  reviewArticle: (articleId: string, perspective: string, outputLanguage: OutputLanguage = "follow_ui") => request<ReviewJob>(localized(`/api/v1/articles/${encodeURIComponent(articleId)}/review`), { method: "POST", body: JSON.stringify({ perspective, outputLanguage }) }),
  getReviewJob: (jobId: string) => request<ReviewJob>(`/api/v1/reviews/${encodeURIComponent(jobId)}`),
  saveReflection: (articleId: string, payload: { markdown?: string; uploadEnabled?: boolean }) =>
    request<{ articleId: string; markdown: string; uploadEnabled: boolean; exists: boolean }>(`/api/v1/articles/${encodeURIComponent(articleId)}/reflection`, {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  createArticleAnnotation: (articleId: string, payload: { quote: string; prefix: string; suffix: string; occurrence: number; note: string }) =>
    request<ArticleAnnotation>(`/api/v1/articles/${encodeURIComponent(articleId)}/annotations`, {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  listArticleAnnotations: (articleId: string) =>
    request<ArticleAnnotations>(`/api/v1/articles/${encodeURIComponent(articleId)}/annotations`),
  updateArticleAnnotation: (articleId: string, annotationId: string, note: string) =>
    request<ArticleAnnotation>(`/api/v1/articles/${encodeURIComponent(articleId)}/annotations/${encodeURIComponent(annotationId)}`, {
      method: "PATCH",
      body: JSON.stringify({ note })
    }),
  deleteArticleAnnotation: (articleId: string, annotationId: string) =>
    request<{ deleted: boolean; annotation: ArticleAnnotation }>(`/api/v1/articles/${encodeURIComponent(articleId)}/annotations/${encodeURIComponent(annotationId)}`, {
      method: "DELETE"
    }),
  polishArticle: (articleId: string, reflectionMarkdown: string) =>
    request<PolishJob>(`/api/v1/articles/${encodeURIComponent(articleId)}/polish`, {
      method: "POST",
      body: JSON.stringify({ reflectionMarkdown })
    }),
  getPolishJob: (jobId: string) => request<PolishJob>(`/api/v1/polish/${encodeURIComponent(jobId)}`),
  getPipelineSettings: () => request<PipelineSettings>(localized("/api/v1/pipeline/settings")),
  updatePipelineSettings: (settings: PipelineSettings) => request<PipelineSettings>(localized("/api/v1/pipeline/settings"), {
    method: "PATCH",
    body: JSON.stringify(settings)
  }),
  getCollections: () => request<{ collections: CollectionNode[] }>(localized("/api/v1/collections")),
  getManagedCollections: () => request<{ collections: CollectionNode[] }>(localized("/api/v1/collections?includeDeleted=true")),
  createCollection: (payload: { name: string; description?: string; parentId?: string }) =>
    request<{ collection: CollectionNode }>(localized("/api/v1/collections"), {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateCollection: (collectionId: string, payload: { name?: string; description?: string; retired?: boolean }) =>
    request<{ collection: CollectionNode }>(localized(`/api/v1/collections/${encodeURIComponent(collectionId)}`), {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  updateArticleCollection: (articleId: string, collectionId?: string) =>
    request(`/api/v1/articles/${encodeURIComponent(articleId)}/collection`, {
      method: "PATCH",
      body: JSON.stringify({ collectionId: collectionId || null })
    }),
  getSettings: () => request<SettingsData>("/api/v1/settings"),
  updateSettings: (settings: SettingsUpdate) =>
    request<SettingsData>("/api/v1/settings", {
      method: "PATCH",
      body: JSON.stringify(settings)
    }),
  activateAIProvider: (providerName: string, settings: SettingsUpdate) =>
    request<SettingsData>("/api/v1/settings/active-provider", {
      method: "PATCH",
      body: JSON.stringify({ providerName, settings })
    }),
  getSettingsSecret: (secret: SettingsSecretTarget, providerName?: string) =>
    request<{ secret: string }>("/api/v1/settings/secrets/reveal", {
      method: "POST",
      body: JSON.stringify({ service: secret, providerName })
    }),
  testSettingsService: (service: "ai" | "firecrawl", providerName?: string, settings?: SettingsUpdate) =>
    request<{ ok: boolean; service: string; provider?: string; model?: string }>("/api/v1/settings/test", {
      method: "POST",
      body: JSON.stringify({ service, providerName, settings })
    }),
  checkHealth: () => request<{ status: string; service: string }>("/health")
};
