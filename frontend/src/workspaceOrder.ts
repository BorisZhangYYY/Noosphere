import type { ArticleSummary } from "./types";

export interface WorkspaceEntry {
  kind: "article" | "collection";
  id: string;
  scopeId: string | null;
}

export function canReorderWorkspace(source: WorkspaceEntry, target: WorkspaceEntry) {
  return source.kind === target.kind && source.scopeId === target.scopeId && source.id !== target.id;
}

export function orderedWorkspaceArticles(articles: ArticleSummary[]) {
  return [...articles].sort((a, b) => (a.workspaceOrder ?? Infinity) - (b.workspaceOrder ?? Infinity));
}
