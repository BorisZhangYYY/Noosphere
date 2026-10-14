import { useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ArticleAnnotation } from "../types";

export interface AnnotationPreviewAnchor { id: string; range: Range; line: number }

export function QuoteAnnotationPreview({ annotation, anchor, onEdit, onClose }: {
  annotation: ArticleAnnotation;
  anchor: AnnotationPreviewAnchor;
  onEdit: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const [position, setPosition] = useState({ left: 12, top: 12, tailLeft: 24, side: "above", visible: false });

  useLayoutEffect(() => {
    const bubble = ref.current;
    if (!bubble) return;
    const reader = anchor.range.startContainer.parentElement?.closest<HTMLElement>(".reader-surface");
    const quoteRect = () => {
      const rects = Array.from(anchor.range.getClientRects());
      return rects[Math.min(anchor.line, rects.length - 1)];
    };
    const place = () => {
      if (!anchor.range.startContainer.isConnected) { closeRef.current(); return; }
      const rect = quoteRect();
      if (!rect) { closeRef.current(); return; }
      const bounds = bubble.getBoundingClientRect();
      const toolbar = document.querySelector(".article-toolbar")?.getBoundingClientRect();
      const readerBounds = reader?.getBoundingClientRect();
      const clipped = reader && getComputedStyle(reader).overflowY === "auto";
      const upper = Math.max(12, toolbar && toolbar.bottom > 0 ? toolbar.bottom + 12 : 12, clipped && readerBounds ? readerBounds.top + 12 : 12);
      const lower = Math.min(window.innerHeight - 12, clipped && readerBounds ? readerBounds.bottom - 12 : window.innerHeight - 12);
      const visible = rect.bottom > upper && rect.top < lower;
      const left = Math.max(12, Math.min(rect.right - 24, window.innerWidth - bounds.width - 12));
      const side = rect.top - bounds.height - 12 >= upper ? "above" : "below";
      const top = Math.max(upper, Math.min(side === "above" ? rect.top - bounds.height - 12 : rect.bottom + 12, lower - bounds.height));
      const tailLeft = Math.max(20, Math.min(rect.right - left - 10, bounds.width - 20));
      const next = { left, top, tailLeft, side, visible };
      setPosition(current => Object.keys(next).every(key => current[key as keyof typeof current] === next[key as keyof typeof next]) ? current : next);
    };
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && bubble.contains(event.target)) return;
      if (Array.from(anchor.range.getClientRects()).some(rect => event.clientX >= rect.left - 2 && event.clientX <= rect.right + 2 && event.clientY >= rect.top - 2 && event.clientY <= rect.bottom + 2)) return;
      closeRef.current();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      closeRef.current();
    };
    const onScroll = (event: Event) => {
      if (event.target instanceof Node && bubble.contains(event.target)) return;
      place();
    };
    const resize = new ResizeObserver(place);
    resize.observe(bubble);
    if (reader) resize.observe(reader);
    place();
    editRef.current?.focus({ preventScroll: true });
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("keydown", escape, true);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", place);
    return () => {
      resize.disconnect();
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("keydown", escape, true);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", place);
    };
  }, [anchor, annotation.note]);

  return createPortal(
    <section ref={ref} className={`annotation-preview-bubble annotation-preview-${position.side}`} role="dialog" aria-label={t("article.quoteViewTitle")}
      style={{ left: position.left, top: position.top, visibility: position.visible ? "visible" : "hidden", "--bubble-tail-left": `${position.tailLeft}px` } as CSSProperties}>
      <header><span>{t("article.quoteEyebrow")}</span><div>
        <button ref={editRef} type="button" onClick={onEdit}>{t("article.quoteEdit")}</button>
        <button type="button" className="annotation-preview-close" aria-label={t("article.quoteClose")} onClick={onClose}>×</button>
      </div></header>
      <div className="annotation-preview-content"><ReactMarkdown remarkPlugins={[remarkGfm]}>{annotation.note}</ReactMarkdown></div>
    </section>, document.body
  );
}
