import type { ArticleDetail, ArticleSummary, CaptureJob, PipelineSettings, ReviewJob, ReviewMode, SettingsData, SettingsSecretTarget, SettingsUpdate, TaxonomyTag, UploadJob } from "./types";

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
  listArticles: () => request<{ articles: ArticleSummary[] }>("/api/v1/articles"),
  getArticle: (articleId: string) => request<ArticleDetail>(`/api/v1/articles/${encodeURIComponent(articleId)}`),
  listCaptureJobs: () => request<{ jobs: CaptureJob[] }>("/api/v1/captures"),
  createCapture: ({ url, reviewMode, perspective }: { url: string; reviewMode: ReviewMode; perspective: string }) => request<CaptureJob>("/api/v1/captures", {
    method: "POST",
    body: JSON.stringify({ url, reviewMode, perspective })
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
  reviewArticle: (articleId: string, perspective: string) => request<ReviewJob>(`/api/v1/articles/${encodeURIComponent(articleId)}/review`, { method: "POST", body: JSON.stringify({ perspective }) }),
  getReviewJob: (jobId: string) => request<ReviewJob>(`/api/v1/reviews/${encodeURIComponent(jobId)}`),
  getPipelineSettings: () => request<PipelineSettings>("/api/v1/pipeline/settings"),
  updatePipelineSettings: (settings: PipelineSettings) => request<PipelineSettings>("/api/v1/pipeline/settings", {
    method: "PATCH",
    body: JSON.stringify(settings)
  }),
  getTaxonomy: () => request<{ tags: TaxonomyTag[] }>("/api/v1/taxonomy"),
  updateArticleClassification: (articleId: string, tagName: string, subtagName?: string) =>
    request(`/api/v1/articles/${encodeURIComponent(articleId)}/classification`, {
      method: "PATCH",
      body: JSON.stringify({ tagName, subtagName: subtagName ?? "" })
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
