export type ArticleStatus = "captured" | "reviewed" | "uploaded" | "failed";
export type CaptureJobStatus = "queued" | "running" | "awaiting_review" | "succeeded" | "failed";
export type ReviewMode = "manual_only" | "ai_then_manual";

export interface CaptureJobEvent {
  id: string;
  at: string;
  stage: "capture" | "image_review" | "ai_review" | "validation" | "classification" | "upload" | "system";
  level: "info" | "success" | "warning" | "error";
  message: string;
  details?: string;
}

export interface CaptureJob {
  id: string;
  url: string;
  status: CaptureJobStatus;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  reviewMode: ReviewMode;
  perspective: string;
  articleId: string | null;
  reviewPreview: string;
  events: CaptureJobEvent[];
  result: { hpath: string; created: boolean } | null;
  error: string | null;
}

export interface ArticleSummary {
  id: string;
  title: string;
  url: string;
  platform: string;
  platformLabel: string;
  author: string | null;
  capturedAt: string | null;
  status: ArticleStatus;
  assetsCount: number;
  classification: ArticleClassification | null;
}

export interface ArticleDetail extends ArticleSummary {
  publishedAt: string | null;
  contentType: string;
  rawMarkdown: string;
  reviewedMarkdown: string;
  displayMarkdown: string;
  validationIssues: string[];
  hasUploaded: boolean;
  activeUpload: UploadJob | null;
  assets: Array<{ name: string; url: string }>;
  removedAssets: Array<{ name: string; url: string; reason: string; source: "ai" | "manual" }>;
  classification: ArticleClassification | null;
}

export interface UploadJob {
  id: string;
  articleId: string;
  target: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: "queued" | "preparing" | "uploading" | "finalizing" | "completed" | "failed";
  progress: number;
  error: string | null;
  result: { created: boolean } | null;
}

export interface ReviewJob {
  id: string;
  articleId: string;
  perspective: string;
  status: "queued" | "running" | "succeeded" | "failed";
  stage: "queued" | "reviewing" | "ai_review" | "validation" | "classification" | "completed" | "failed";
  progress: number;
  reviewPreview: string;
  events: CaptureJobEvent[];
  error: string | null;
}

export interface ArticleClassification {
  article_id: string;
  reason: string;
  tag_id: string;
  tag_name: string;
  subtag_id: string | null;
  subtag_name: string | null;
}

export interface TaxonomyTag {
  id: string;
  name: string;
  description: string;
  parent_id: string | null;
  children: TaxonomyTag[];
}

export interface PipelinePerspective {
  id: string;
  label: string;
  description: string;
  prompt: string;
  template: string;
}

export interface PipelineSettings {
  reviewMode: ReviewMode;
  activePerspective: string;
  commonPrompt: string;
  perspectives: PipelinePerspective[];
}

export type AIApiFormat = "anthropic" | "openai_chat" | "openai_responses";
export type AIProviderType = "kimi" | "minimax" | "zhipu" | "volcengine" | "custom";

export interface AIProviderSettings {
  name: string;
  providerType: AIProviderType;
  apiFormat: AIApiFormat;
  model: string;
  apiBase: string;
  apiKeyConfigured: boolean;
  apiKey?: string;
}

export interface SettingsData {
  aiProvider: string;
  aiProviders: AIProviderSettings[];
  crawlerPrimary: string;
  crawlerFallback: string;
  firecrawlApiKeyConfigured: boolean;
  siyuanApiBase: string;
  siyuanParentId: string;
  siyuanTokenConfigured: boolean;
  localArchiveEnabled: boolean;
  localArchiveOutputDir: string;
}

export interface SettingsUpdate extends SettingsData {
  firecrawlApiKey?: string;
  siyuanToken?: string;
}

export type SettingsSecretTarget = "ai" | "firecrawl" | "siyuan";
