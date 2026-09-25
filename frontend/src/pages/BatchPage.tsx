import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { BatchForm, batchStatusLabels } from "../components/BatchForm";
import { ErrorPanel } from "../components/StatePanel";

export function BatchPage() {
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [filter, setFilter] = useState("");
  const history = useQuery({ queryKey: ["batches"], queryFn: api.listBatches, refetchInterval: 2000 });
  const action = useMutation({ mutationFn: ({ id, name, itemIds }: { id: string; name: string; itemIds?: string[] }) => api.controlBatch(id, name, itemIds), onSuccess: () => client.invalidateQueries({ queryKey: ["batches"] }) });
  const current = history.data?.batches.find(b => b.id === params.get("batch"));
  const labels = batchStatusLabels(Boolean(zh));
  function exportFailures() {
    const lines = (current?.items ?? []).filter(item => ["failed", "invalid"].includes(item.status)).map(item => `${item.url}\n# ${(item.error ?? "").replace(/[\r\n]+/g, " ")}`).join("\n");
    const url = URL.createObjectURL(new Blob([lines], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = "noosphere-failed-urls.txt"; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <main className="page discovery-page">
    <header className="discovery-header"><p className="context-label">{zh ? "批量抓取" : "Batch capture"}</p><h1>{zh ? "批量工作台" : "Batch workspace"}</h1><p>{zh ? "一次提交多篇文章，逐项查看进度。默认跳过重复链接和已收录文章。" : "Process multiple articles and follow each item. Duplicates and existing articles are skipped."}</p></header>
    <BatchForm onCreated={job => setParams({ batch: job.id })} />
    {(action.error || history.error) && <ErrorPanel message={String(action.error || history.error)} />}
    <section className="batch-history">
      <div className="batch-history-heading"><div><p className="context-label">{zh ? "处理记录" : "Processing log"}</p><h2>{zh ? "任务记录" : "Batch history"}</h2></div><select aria-label={zh ? "选择批次" : "Select batch"} value={current?.id ?? ""} onChange={e => setParams({ batch: e.target.value })}><option value="">{zh ? "选择批次" : "Choose a batch"}</option>{history.data?.batches.map(b => <option key={b.id} value={b.id}>{new Date(b.createdAt).toLocaleString()} · {labels[b.status]} · {b.items.length}</option>)}</select></div>
    {!current && !history.isLoading && <div className="discovery-empty compact"><h3>{zh ? "选择一个批次查看进度" : "Choose a batch to view progress"}</h3><p>{zh ? "新建批次后也会自动显示在这里。" : "New batches appear here automatically."}</p></div>}
    {current && <><div className="batch-status-line" role="status"><strong>{labels[current.status]}</strong><span>{current.items.filter(i => ["succeeded", "skipped"].includes(i.status)).length}/{current.items.length}</span>{current.pauseRequested && current.status === "running" ? <small>{zh ? "当前步骤结束后暂停" : "Pausing after current stage"}</small> : null}{current.cancelRequested && current.status === "running" ? <small>{zh ? "当前步骤结束后取消" : "Cancelling after current stage"}</small> : null}</div>
    {current.error && <ErrorPanel message={current.error} />}
    <div className="batch-toolbar">{([['pause', zh ? '暂停' : 'Pause'], ['resume', zh ? '继续待处理项' : 'Resume pending'], ['retry', zh ? '重试失败项' : 'Retry failed'], ['cancel', zh ? '取消待处理项' : 'Cancel pending']] as const).map(([name, label]) => <button className="button-secondary" type="button" key={name} disabled={action.isPending || (name === 'pause' ? !['queued', 'running'].includes(current.status) : ['resume', 'retry'].includes(name) ? ['queued', 'running', 'cancelled'].includes(current.status) : current.status === 'cancelled')} onClick={() => action.mutate({ id: current.id, name })}>{label}</button>)}<button className="button-secondary" type="button" onClick={exportFailures}>{zh ? "导出失败链接" : "Export failures"}</button><select aria-label={zh ? "按状态筛选" : "Filter status"} value={filter} onChange={e => setFilter(e.target.value)}><option value="">{zh ? "全部状态" : "All statuses"}</option>{['pending', 'running', 'succeeded', 'failed', 'invalid', 'skipped', 'cancelled'].map(s => <option key={s} value={s}>{labels[s]}</option>)}</select></div>
    <div className="batch-table-wrap"><table className="batch-table"><thead><tr><th>{zh ? "文章链接" : "URL"}</th><th>{zh ? "阶段" : "Stage"}</th><th>{zh ? "状态" : "Status"}</th><th>{zh ? "详情" : "Details"}</th></tr></thead><tbody>{current.items.filter(i => !filter || i.status === filter).map(item => <tr key={item.id}><td>{item.articleId ? <Link to={`/articles/${encodeURIComponent(item.articleId)}`}>{item.url}</Link> : item.url}</td><td>{labels[item.stage]}</td><td>{labels[item.status]}</td><td>{item.error || (item.reason ? labels[item.reason] : '')}{item.status === 'failed' && <button type="button" disabled={action.isPending || ['queued', 'running'].includes(current.status)} onClick={() => action.mutate({ id: current.id, name: 'retry', itemIds: [item.id] })}>{zh ? '重试此项' : 'Retry item'}</button>}</td></tr>)}</tbody></table></div></>}
    </section>
  </main>;
}
