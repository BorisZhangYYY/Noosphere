import i18n from "./i18n";
import type { ArticleDetail, ArticleSummary, CaptureJob, OutputLanguage, PipelineSettings, ReviewJob, ReviewMode, SettingsData, SettingsSecretTarget, SettingsUpdate, TaxonomyTag, TrashedArticle, UploadJob } from "./types";

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
    throw new Error(payload.error ?? `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  listArticles: () => request<{ articles: ArticleSummary[] }>(localized("/api/v1/articles")),
  getArticle: (articleId: string) => request<ArticleDetail>(localized(`/api/v1/articles/${encodeURIComponent(articleId)}`)),
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
  saveReviewedMarkdown: (articleId: string, reviewedMarkdown: string) =>
    request<{ ok: boolean }>(`/api/v1/articles/${encodeURIComponent(articleId)}`, {
      method: "PATCH",
      body: JSON.stringify({ reviewedMarkdown })
    }),
  updateArticleImage: (articleId: string, assetName: string, state: "active" | "removed", reviewedMarkdown: string) =>
    request<{ ok: boolean; name: string; state: "active" | "removed" }>(`/api/v1/articles/${encodeURIComponent(articleId)}/images/${encodeURIComponent(assetName)}`, {
      method: "PATCH",
      body: JSON.stringify({ state, reviewedMarkdown })
    }),
  uploadArticle: (articleId: string) =>
    request<UploadJob>(`/api/v1/articles/${encodeURIComponent(articleId)}/upload`, {
      method: "POST",
      body: JSON.stringify({ target: "siyuan" })
    }),
  getUploadJob: (jobId: string) => request<UploadJob>(`/api/v1/uploads/${encodeURIComponent(jobId)}`),
  reviewArticle: (articleId: string, perspective: string, outputLanguage: OutputLanguage = "follow_ui") => request<ReviewJob>(localized(`/api/v1/articles/${encodeURIComponent(articleId)}/review`), { method: "POST", body: JSON.stringify({ perspective, outputLanguage }) }),
  getReviewJob: (jobId: string) => request<ReviewJob>(`/api/v1/reviews/${encodeURIComponent(jobId)}`),
  getPipelineSettings: () => request<PipelineSettings>(localized("/api/v1/pipeline/settings")),
  updatePipelineSettings: (settings: PipelineSettings) => request<PipelineSettings>(localized("/api/v1/pipeline/settings"), {
    method: "PATCH",
    body: JSON.stringify(settings)
  }),
  getTaxonomy: () => request<{ tags: TaxonomyTag[] }>(localized("/api/v1/taxonomy")),
  getManagedTaxonomy: () => request<{ tags: TaxonomyTag[] }>(localized("/api/v1/taxonomy?includeRetired=true")),
  createTaxonomyCategory: (payload: { name: string; description: string; parentId?: string }) =>
    request<{ category: TaxonomyTag }>(localized("/api/v1/taxonomy/categories"), {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  updateTaxonomyCategory: (tagId: string, payload: { name?: string; description?: string; retired?: boolean }) =>
    request<{ category: TaxonomyTag }>(localized(`/api/v1/taxonomy/categories/${encodeURIComponent(tagId)}`), {
      method: "PATCH",
      body: JSON.stringify(payload)
    }),
  updateArticleClassification: (articleId: string, tagId: string, subtagId?: string) =>
    request(localized(`/api/v1/articles/${encodeURIComponent(articleId)}/classification`), {
      method: "PATCH",
      body: JSON.stringify({ tagId, subtagId })
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
