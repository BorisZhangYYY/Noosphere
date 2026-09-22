import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { ErrorPanel } from "../components/StatePanel";
import type { CollectionNode } from "../types";

function collectionOptions(nodes: CollectionNode[], prefix = ""): { id: string; label: string }[] { return nodes.flatMap(node => [{ id: node.id, label: prefix + node.name }, ...collectionOptions(node.children, prefix + node.name + " / ")]); }

export function BatchPage() {
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState("");
  const [mode, setMode] = useState("capture");
  const [language, setLanguage] = useState("source");
  const [collectionId, setCollectionId] = useState("");
  const [filter, setFilter] = useState("");
  const [fileError, setFileError] = useState("");
  const urls = text.split(/\r?\n/).map(s => s.trim()).filter(s => s && !s.startsWith("#"));
  const history = useQuery({ queryKey: ["batches"], queryFn: api.listBatches, refetchInterval: 2000 });
  const collections = useQuery({ queryKey: ["collections", i18n.resolvedLanguage], queryFn: api.getCollections });
  const preview = useMutation({ mutationFn: api.previewBatch });
  const create = useMutation({ mutationFn: api.createBatch, onSuccess: job => { setParams({ batch: job.id }); client.invalidateQueries({ queryKey: ["batches"] }); } });
  const action = useMutation({ mutationFn: ({ id, name, itemIds }: { id: string; name: string; itemIds?: string[] }) => api.controlBatch(id, name, itemIds), onSuccess: () => client.invalidateQueries({ queryKey: ["batches"] }) });
  const current = history.data?.batches.find(b => b.id === params.get("batch"));
  const labels: Record<string, string> = zh ? { pending: "待处理", queued: "排队中", running: "处理中", paused: "已暂停", succeeded: "已完成", failed: "失败", skipped: "已跳过", invalid: "无效链接", cancelled: "已取消", capture: "抓取", review: "校对", placement: "归类", completed: "完成", duplicate: "批内重复", existing: "已收录" } : { pending: "Pending", queued: "Queued", running: "Running", paused: "Paused", succeeded: "Completed", failed: "Failed", skipped: "Skipped", invalid: "Invalid URL", cancelled: "Cancelled", capture: "Capture", review: "Review", placement: "Placement", completed: "Completed", duplicate: "Duplicate", existing: "Already captured" };
  function exportFailures() {
    const lines = (current?.items ?? []).filter(item => ["failed", "invalid"].includes(item.status)).map(item => `${item.url}\n# ${(item.error ?? "").replace(/[\r\n]+/g, " ")}`).join("\n");
    const url = URL.createObjectURL(new Blob([lines], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "noosphere-failed-urls.txt"; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <main className="page discovery-page">
    <header><h1>{zh ? "批量工作台" : "Batch workspace"}</h1><p>{zh ? "一次提交多篇文章，逐项查看进度。默认跳过重复链接和已收录文章。" : "Process multiple articles and follow each item. Duplicates and existing articles are skipped."}</p></header>
    <form className="batch-form" onSubmit={e => { e.preventDefault(); create.mutate({ urls, mode, language, collectionId }); }}>
      <label>{zh ? "每行一个链接（最多 100 条）" : "One URL per line (up to 100)"}<textarea rows={6} value={text} onChange={e => { setText(e.target.value); preview.reset(); }} /></label>
      <label>{zh ? "导入文本文件" : "Import text file"}<input type="file" accept=".txt,text/plain" onChange={async e => { const file = e.target.files?.[0]; if (!file) return; if (file.size > 1024 * 1024) { setFileError(zh ? "文件不能超过 1 MB" : "File must be under 1 MB"); return; } setFileError(""); setText(await file.text()); preview.reset(); }} /></label>
      <div className="discovery-filters"><label>{zh ? "处理方式" : "Workflow"}<select value={mode} onChange={e => setMode(e.target.value)}><option value="capture">{zh ? "仅抓取" : "Capture only"}</option><option value="review">{zh ? "抓取并 AI 校对" : "Capture and AI review"}</option></select></label>
      <label>{zh ? "输出语言" : "Output language"}<select value={language} onChange={e => setLanguage(e.target.value)}><option value="source">{zh ? "跟随原文" : "Source language"}</option><option value="zh-CN">简体中文</option><option value="en-US">English</option></select></label>
      <label>{zh ? "目标分类" : "Collection"}<select value={collectionId} onChange={e => setCollectionId(e.target.value)}><option value="">{zh ? "未分类" : "Unfiled"}</option>{collectionOptions(collections.data?.collections ?? []).map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label></div>
      {mode === "review" && <p>{zh ? "使用提交时的当前模型和校对视角。配置变化后会停止后续处理，避免使用不同设置继续。" : "Uses the current model and perspective. A configuration change stops subsequent processing."}</p>}
      <div className="discovery-toolbar"><button type="button" disabled={!urls.length || urls.length > 100 || preview.isPending} onClick={() => preview.mutate(urls)}>{zh ? "检查链接" : "Check URLs"}</button><button type="submit" disabled={!urls.length || urls.length > 100 || create.isPending}>{zh ? "开始处理" : "Start batch"}</button></div>
    </form>
    {fileError && <ErrorPanel message={fileError} />}
    {(preview.error || create.error || action.error || history.error) && <ErrorPanel message={String(preview.error || create.error || action.error || history.error)} />}
    {preview.data && <div className="batch-preview" aria-live="polite">{preview.data.items.map(item => <p key={item.id}>{labels[item.status]} · {item.url} {item.reason ? `— ${labels[item.reason]}` : item.error}</p>)}</div>}
    <section><h2>{zh ? "任务记录" : "Batch history"}</h2><select aria-label={zh ? "选择批次" : "Select batch"} value={current?.id ?? ""} onChange={e => setParams({ batch: e.target.value })}><option value="">{zh ? "选择批次" : "Choose a batch"}</option>{history.data?.batches.map(b => <option key={b.id} value={b.id}>{new Date(b.createdAt).toLocaleString()} · {labels[b.status]} · {b.items.length}</option>)}</select>
    {current && <><p role="status">{labels[current.status]} · {current.items.filter(i => ["succeeded", "skipped"].includes(i.status)).length}/{current.items.length}{current.pauseRequested && current.status === "running" ? (zh ? " · 当前步骤结束后暂停" : " · Pausing after current stage") : ""}{current.cancelRequested && current.status === "running" ? (zh ? " · 当前步骤结束后取消" : " · Cancelling after current stage") : ""}</p>
    {current.error && <ErrorPanel message={current.error} />}
    <div className="discovery-toolbar">{([['pause', zh ? '暂停' : 'Pause'], ['resume', zh ? '继续待处理项' : 'Resume pending'], ['retry', zh ? '重试失败项' : 'Retry failed'], ['cancel', zh ? '取消待处理项' : 'Cancel pending']] as const).map(([name, label]) => <button type="button" key={name} disabled={action.isPending || (name === 'pause' ? !['queued', 'running'].includes(current.status) : ['resume', 'retry'].includes(name) ? ['queued', 'running', 'cancelled'].includes(current.status) : current.status === 'cancelled')} onClick={() => action.mutate({ id: current.id, name })}>{label}</button>)}<button type="button" onClick={exportFailures}>{zh ? "导出失败链接" : "Export failures"}</button><select aria-label={zh ? "按状态筛选" : "Filter status"} value={filter} onChange={e => setFilter(e.target.value)}><option value="">{zh ? "全部状态" : "All statuses"}</option>{['pending', 'running', 'succeeded', 'failed', 'invalid', 'skipped', 'cancelled'].map(s => <option key={s} value={s}>{labels[s]}</option>)}</select></div>
    <div className="batch-table-wrap"><table className="batch-table"><thead><tr><th>{zh ? "文章链接" : "URL"}</th><th>{zh ? "阶段" : "Stage"}</th><th>{zh ? "状态" : "Status"}</th><th>{zh ? "详情" : "Details"}</th></tr></thead><tbody>{current.items.filter(i => !filter || i.status === filter).map(item => <tr key={item.id}><td>{item.articleId ? <Link to={`/articles/${encodeURIComponent(item.articleId)}`}>{item.url}</Link> : item.url}</td><td>{labels[item.stage]}</td><td>{labels[item.status]}</td><td>{item.error || (item.reason ? labels[item.reason] : '')}{item.status === 'failed' && <button type="button" disabled={action.isPending || ['queued', 'running'].includes(current.status)} onClick={() => action.mutate({ id: current.id, name: 'retry', itemIds: [item.id] })}>{zh ? '重试此项' : 'Retry item'}</button>}</td></tr>)}</tbody></table></div></>}
    </section>
  </main>;
}
