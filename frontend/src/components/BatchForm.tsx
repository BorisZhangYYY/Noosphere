import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { ErrorPanel } from "./StatePanel";
import type { BatchJob, CollectionNode } from "../types";

export function collectionOptions(nodes: CollectionNode[], prefix = ""): { id: string; label: string }[] {
  return nodes.flatMap(node => [{ id: node.id, label: prefix + node.name }, ...collectionOptions(node.children, prefix + node.name + " / ")]);
}

export const batchStatusLabels = (zh: boolean): Record<string, string> => zh
  ? { pending: "待处理", queued: "排队中", running: "处理中", paused: "已暂停", succeeded: "已完成", failed: "失败", skipped: "已跳过", invalid: "无效链接", cancelled: "已取消", capture: "抓取", review: "校对", placement: "归类", completed: "完成", duplicate: "批内重复", existing: "已收录" }
  : { pending: "Pending", queued: "Queued", running: "Running", paused: "Paused", succeeded: "Completed", failed: "Failed", skipped: "Skipped", invalid: "Invalid URL", cancelled: "Cancelled", capture: "Capture", review: "Review", placement: "Placement", completed: "Completed", duplicate: "Duplicate", existing: "Already captured" };

export function BatchForm({ onCreated, compact = false }: { onCreated: (job: BatchJob) => void; compact?: boolean }) {
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const client = useQueryClient();
  const [text, setText] = useState("");
  const [mode, setMode] = useState("capture");
  const [language, setLanguage] = useState("source");
  const [collectionId, setCollectionId] = useState("");
  const [fileError, setFileError] = useState("");
  const urls = text.split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith("#"));
  const collections = useQuery({ queryKey: ["collections", i18n.resolvedLanguage], queryFn: api.getCollections });
  const preview = useMutation({ mutationFn: api.previewBatch });
  const create = useMutation({
    mutationFn: api.createBatch,
    onSuccess: job => {
      client.invalidateQueries({ queryKey: ["batches"] });
      onCreated(job);
    }
  });
  const labels = batchStatusLabels(Boolean(zh));
  const limitError = urls.length > 100 ? (zh ? `一次最多处理 100 条链接，当前有 ${urls.length} 条。` : `A batch can contain up to 100 URLs; this list has ${urls.length}.`) : "";

  return (
    <form className={`batch-form${compact ? " batch-form-compact" : ""}`} onSubmit={e => { e.preventDefault(); create.mutate({ urls, mode, language, collectionId }); }}>
      <label className="batch-url-field"><span>{zh ? "文章链接" : "Article URLs"}<small>{zh ? "每行一个，最多 100 条" : "One per line, up to 100"}</small></span>
        <textarea rows={compact ? 5 : 6} value={text} onChange={e => { setText(e.target.value); preview.reset(); }} placeholder="https://mp.weixin.qq.com/s/…" aria-describedby={limitError ? "batch-limit-error" : undefined} />
      </label>
      <label className="batch-file-field"><span>{zh ? "也可以导入文本文件" : "Or import a text file"}</span>
        <input type="file" accept=".txt,text/plain" onChange={async e => { const file = e.target.files?.[0]; if (!file) return; if (file.size > 1024 * 1024) { setFileError(zh ? "文件不能超过 1 MB" : "File must be under 1 MB"); return; } setFileError(""); setText(await file.text()); preview.reset(); }} />
      </label>
      <div className="batch-options">
        <label>{zh ? "处理方式" : "Workflow"}
          <select value={mode} onChange={e => setMode(e.target.value)}>
            <option value="capture">{zh ? "仅抓取" : "Capture only"}</option>
            <option value="review">{zh ? "抓取并 AI 校对" : "Capture and AI review"}</option>
          </select>
        </label>
        <label>{zh ? "输出语言" : "Output language"}
          <select value={language} onChange={e => setLanguage(e.target.value)}>
            <option value="source">{zh ? "跟随原文" : "Source language"}</option>
            <option value="zh-CN">简体中文</option>
            <option value="en-US">English</option>
          </select>
        </label>
        <label>{zh ? "目标分类" : "Collection"}
          <select value={collectionId} onChange={e => setCollectionId(e.target.value)}>
            <option value="">{zh ? "未分类" : "Unfiled"}</option>
            {collectionOptions(collections.data?.collections ?? []).map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </label>
      </div>
      {mode === "review" && <p className="batch-form-note">{zh ? "使用提交时的当前模型和校对视角。配置变化后会停止后续处理，避免使用不同设置继续。" : "Uses the current model and perspective. A configuration change stops subsequent processing."}</p>}
      <div className="batch-form-actions">
        <span>{urls.length ? (zh ? `${urls.length} 条链接` : `${urls.length} URL${urls.length === 1 ? "" : "s"}`) : (zh ? "尚未添加链接" : "No URLs added")}</span>
        <div>
          <button className="button-secondary" type="button" disabled={!urls.length || urls.length > 100 || preview.isPending} onClick={() => preview.mutate(urls)}>{zh ? "检查链接" : "Check URLs"}</button>
          <button className="button-primary" type="submit" disabled={!urls.length || urls.length > 100 || create.isPending}>{zh ? "开始处理" : "Start batch"}</button>
        </div>
      </div>
      {limitError && <p className="batch-limit-error" id="batch-limit-error" role="alert">{limitError}</p>}
      {fileError && <ErrorPanel message={fileError} />}
      {(preview.error || create.error) && <ErrorPanel message={String(preview.error || create.error)} />}
      {preview.data && <div className="batch-preview" aria-live="polite">{preview.data.items.map(item => <p key={item.id}>{labels[item.status]} · {item.url} {item.reason ? `— ${labels[item.reason]}` : item.error}</p>)}</div>}
    </form>
  );
}
