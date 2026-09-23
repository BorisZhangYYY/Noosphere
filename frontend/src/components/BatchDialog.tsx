import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { X } from "@phosphor-icons/react";
import { BatchForm } from "./BatchForm";

export function BatchDialog({ onClose }: { onClose: () => void }) {
  const { i18n } = useTranslation();
  const zh = i18n.resolvedLanguage?.startsWith("zh");
  const navigate = useNavigate();

  return (
    <div className="dialog-layer modal-root-layer" role="presentation" onMouseDown={onClose}>
      <section
        className="capture-dialog batch-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="batch-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="dialog-close" onClick={onClose} aria-label={zh ? "关闭" : "Close"}>
          <X size={19} />
        </button>
        <p className="context-label">{zh ? "批量处理" : "Batch"}</p>
        <h2 id="batch-dialog-title">{zh ? "一次提交多篇文章" : "Capture multiple articles"}</h2>
        <p>{zh ? "粘贴链接或导入文本文件。默认跳过重复链接和已收录文章，逐项进度在批量工作台查看。" : "Paste links or import a text file. Duplicates and existing articles are skipped; follow progress in the batch workspace."}</p>
        <BatchForm onCreated={(job) => { onClose(); navigate(`/batches?batch=${encodeURIComponent(job.id)}`); }} />
      </section>
    </div>
  );
}
