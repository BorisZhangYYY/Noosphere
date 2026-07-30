export type ArticleStatus = "captured" | "reviewed" | "uploaded" | "failed";
export type CaptureJobStatus = "queued" | "running" | "awaiting_review" | "succeeded" | "recovered" | "failed";
export type ReviewMode = "auto_upload" | "ai_then_manual";
export type OutputLanguage = "follow_ui" | "zh-CN" | "en-US" | "source";

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
  outputLanguage: OutputLanguage | "zh-CN" | "en-US" | "source";
  articleId: string | null;
  reviewPreview: string;
  events: CaptureJobEvent[];
  result: { hpath: string; created: boolean } | null;
  error: string | null;
  originalError?: string | null;
  recoveredAt?: string | null;
  recoveredByReviewJobId?: string | null;
  retryOfJobId?: string | null;
  retriedByJobId?: string | null;
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
  collection: ArticleCollection | null;
  operationSummary: ArticleOperationSummary;
  searchTerms: string[];
}

export interface TrashedArticle {
  id: string;
  title: string;
  url: string;
  deletedAt: string;
  details: {
    platform?: string;
    platformLabel?: string;
    capturedAt?: string | null;
    assetsCount?: number;
  };
}

export interface ArticleDetail extends ArticleSummary {
  publishedAt: string | null;
  contentType: string;
  rawMarkdown: string;
  reviewedMarkdown: string;
  displayMarkdown: string;
  editableMarkdown: string;
  metadata: Record<"source" | "platform" | "author" | "publishedAt" | "capturedAt" | "contentType", {
    value: string;
    editable: boolean;
    origin: "source" | "missing" | "manual" | "ai" | string;
    evidence: string;
    model: string;
    provider: string;
    updatedAt: string | null;
  }>;
  metadataHistory: Array<{
    field: string;
    action: "accepted" | "reverted" | string;
    source: "manual" | "ai" | string;
    value: string;
    evidence: string;
    model?: string;
    provider?: string;
    reason?: string;
    at: string;
  }>;
  validationIssues: string[];
  hasUploaded: boolean;
  activeUpload: UploadJob | null;
  activeReview: ReviewJob | null;
  assets: Array<{ name: string; url: string }>;
  removedAssets: Array<{ name: string; url: string; reason: string; source: "ai" | "manual" }>;
  collection: ArticleCollection | null;
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

export interface ArticleCollection {
  article_id: string;
  reason: string;
  collection_id: string | null;
  collection_name: string | null;
  collection_path: Array<{ id: string; name: string }>;
  confidence: number;
  source: "ai" | "manual" | string;
  updated_at: string | null;
}

export interface ArticleOperationSummary {
  captureCount: number;
  reviewCount: number;
  rereviewCount: number;
  uploadCount: number;
  events: Array<{ id: string; type: "capture" | "review" | "upload"; at: string; details: Record<string, unknown> }>;
}

export interface CollectionNode {
  id: string;
  name: string;
  description: string;
  parent_id: string | null;
  retired: boolean;
  direct_article_count: number;
  article_count: number;
  children: CollectionNode[];
}

export interface PipelinePerspective {
  id: string;
  label: string;
  description: string;
  prompt: string;
  template: string;
  builtin: boolean;
  editable: boolean;
  outputSections: Record<string, string>;
  bodySection: string;
}

export interface PipelineSettings {
  reviewMode: ReviewMode;
  outputLanguage: OutputLanguage;
  language: "zh-CN" | "en-US";
  activePerspective: string;
  commonPrompt: string;
  commonEditable: boolean;
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
  visionCapable: boolean;
  apiKey?: string;
}

export interface SettingsData {
  aiProvider: string;
  imageProvider: string;
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
