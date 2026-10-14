import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Vditor from "vditor";
import "vditor/dist/index.css";
import "./MarkdownEditor.css";
import { useTheme } from "../theme";
import type { ArticleAnnotation, QuoteAnchorDraft } from "../types";
import { createImageDropResolver, dragScrollDistance, dragScrollVelocity, imageDropMarkdown, nearestDragBlock, preserveDraggedImageReferences } from "../imageDrag";
import { captureBlockSelection, createBlockDropResolver, isMovableArticleBlock, isMovableMarkdownBlock, moveMappedBlockMarkdown, articleBlockMap, restoreBlockSelection, remapMovedRange, reconcileBlockEdits, markdownStateKey, markdownBlocks, headingSectionEnd, articleBlockMovePlan } from "../blockDrag";
import { installBlockControls } from "./blockControls";
import { createHeadingFolds } from "./headingFolds";
import { QuoteAnnotationPreview, type AnnotationPreviewAnchor } from "./QuoteAnnotationPreview";

interface MarkdownEditorProps {
  articleId: string;
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  removedAssetNames?: string[];
  showRemovedImages?: boolean;
  onDeleteImage?: (assetName: string) => void;
  onRestoreImage?: (assetName: string) => void;
  annotations?: ArticleAnnotation[];
  annotationSourceDigest?: string;
  onSelectQuote?: (selection: QuoteAnchorDraft | null) => void;
  onOpenAnnotation?: (annotationId: string) => void;
  onResolvedAnnotationIds?: (annotationIds: string[]) => void;
  focusAnnotationRequest?: { id: string; token: number } | null;
}

const EDITOR_IMAGE_ACTION_RE = /[ \t]*<button\b[^>]*\bclass\s*=\s*["'][^"']*\bnoosphere-image-action\b[^"']*["'][^>]*>.*?<\/button>[ \t]*\n?/gis;
const MARKDOWN_IMAGE_TARGET_RE = /!\[[^\]\n]*]\(\s*(?:<([^>\n]+)>|([^\s)\n]+))[^)\n]*\)|<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;
const STRUCTURAL_POPOVER_TYPES = new Set(["blockquote", "li", "heading", "block", "footnotes-block", "vditor-toc"]);

function stripEditorArtifacts(markdown: string) {
  return markdown.replace(EDITOR_IMAGE_ACTION_RE, "");
}

function imageStructure(markdown: string) {
  return Array.from(stripEditorArtifacts(markdown).matchAll(MARKDOWN_IMAGE_TARGET_RE), (match) => match[1] || match[2] || match[3] || "");
}

function hasSameImageStructure(candidate: string, reference: string) {
  const candidateImages = imageStructure(candidate);
  const referenceImages = imageStructure(reference);
  return candidateImages.length === referenceImages.length
    && candidateImages.every((image, index) => image === referenceImages[index]);
}

export function MarkdownEditor({ articleId, value, onChange, readOnly, removedAssetNames = [], showRemovedImages = true, onDeleteImage, onRestoreImage, annotations = [], annotationSourceDigest = "", onSelectQuote, onOpenAnnotation, onResolvedAnnotationIds, focusAnnotationRequest }: MarkdownEditorProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<Vditor | null>(null);
  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  const removedNamesRef = useRef(new Set(removedAssetNames));
  const readOnlyRef = useRef(readOnly);
  const decorateImagesRef = useRef<() => void>(() => undefined);
  const decorateAnnotationsRef = useRef<() => void>(() => undefined);
  const focusAnnotationRef = useRef<(annotationId: string) => void>(() => undefined);
  const [annotationPreview, setAnnotationPreview] = useState<AnnotationPreviewAnchor | null>(null);
  const closeAnnotationPreview = () => setAnnotationPreview(null);
  const imageActionsRef = useRef({ onDeleteImage, onRestoreImage });
  const annotationPropsRef = useRef({ annotations, annotationSourceDigest, onSelectQuote, onOpenAnnotation, onResolvedAnnotationIds });
  const restoringImageStructureRef = useRef(false);
  const applyingExternalValueRef = useRef(false);
  const structuralHistoryRef = useRef(new Map<string, string>());
  const { i18n, t } = useTranslation();
  const { resolvedTheme } = useTheme();
  const resolvedThemeRef = useRef(resolvedTheme);

  onChangeRef.current = onChange;
  valueRef.current = value;
  removedNamesRef.current = new Set(removedAssetNames);
  readOnlyRef.current = readOnly;
  resolvedThemeRef.current = resolvedTheme;
  imageActionsRef.current = { onDeleteImage, onRestoreImage };
  annotationPropsRef.current = { annotations, annotationSourceDigest, onSelectQuote, onOpenAnnotation, onResolvedAnnotationIds };

  useEffect(() => {
    if (!hostRef.current) return;
    const host = hostRef.current;
    structuralHistoryRef.current.clear();
    let cancelled = false;
    let editor: Vditor | null = null;
    let observer: MutationObserver | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let decorationFrame = 0;
    let annotationFrame = 0;
    const annotationRanges = new Map<string, Range>();
    const highlightName = "noosphere-article-annotations";
    const actions = new Map<string, HTMLDivElement>();
    let blockControls: ReturnType<typeof installBlockControls> | null = null;
    const headingFolds = createHeadingFolds({
      root: () => host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset"),
      readOnly: () => readOnlyRef.current,
      serialize: html => editorRef.current?.vditor.lute.VditorDOM2Md(html) ?? html,
    });
    const foldHistory = new Map<string, number[]>();
    const rememberFolds = (markdown: string, indices: number[]) => {
      foldHistory.set(markdownStateKey(markdown), indices);
      if (foldHistory.size > 160) foldHistory.delete(foldHistory.keys().next().value!);
    };
    const rememberStructuralValue = (canonical: string, markdown: string) => {
      structuralHistoryRef.current.set(markdownStateKey(canonical), markdown);
      if (structuralHistoryRef.current.size > 160) structuralHistoryRef.current.delete(structuralHistoryRef.current.keys().next().value!);
    };
    const copyText = async (text: string) => {
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(text);
          return;
        } catch {
          // Fall through to the browser-compatible selection path.
        }
      }
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.append(textarea);
      textarea.select();
      document.execCommand("copy");
      textarea.remove();
    };
    const imageName = (source: string) => {
      try {
        const pathname = new URL(source, window.location.origin).pathname;
        return decodeURIComponent(pathname.split("/").pop() ?? "");
      } catch {
        return "";
      }
    };
    let dragging: {
      kind: "image" | "block"; index: number; value: string; source: HTMLElement; root: HTMLElement;
      scrollContainer: Element; scrollBounds: { top: number; bottom: number };
      blocks: Map<HTMLElement, Array<{ element: HTMLElement; top: number; bottom: number }>>;
      resolve: ReturnType<typeof createImageDropResolver>;
      layoutDirty: boolean;
      block?: { markdown: string; editorValue: string; sourcePath: number[]; mapping: Map<HTMLElement, number[]>;
        selection: ReturnType<typeof captureBlockSelection>; validDrops: Map<string, boolean>;
        sourceEnd: number; folded: number[]; blocks: ReturnType<typeof markdownBlocks> };
    } | null = null;
    let dropPosition: { target: HTMLElement; side: "before" | "after" } | null = null;
    let dragPointer: { x: number; y: number; fallback: Element | null } | null = null;
    let dragFrame = 0;
    let lastDragFrameTime = 0;
    let dragPreview: HTMLCanvasElement | null = null;
    const frameBounds = new Map<Node, DOMRect>();
    const boundsFor = (node: Node) => {
      let bounds = frameBounds.get(node);
      if (!bounds) {
        if (node instanceof Element) bounds = node.getBoundingClientRect();
        else {
          const range = document.createRange();
          range.selectNode(node);
          bounds = range.getBoundingClientRect();
        }
        frameBounds.set(node, bounds);
      }
      return bounds;
    };
    const dropLine = document.createElement("div");
    dropLine.className = "noosphere-image-drop-line";
    dropLine.hidden = true;
    dropLine.setAttribute("aria-hidden", "true");
    actionsRef.current?.append(dropLine);
    const moveImage = (index: number, target: HTMLElement, side: "before" | "after") => {
      if (readOnlyRef.current) return;
      const root = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      const currentEditor = editorRef.current;
      if (!root || !currentEditor) return;
      const nextMarkdown = imageDropMarkdown(root, index, target, side,
        html => currentEditor.vditor.lute.VditorDOM2Md(html), valueRef.current);
      if (!nextMarkdown || nextMarkdown === valueRef.current) return;
      const previous = stripEditorArtifacts(currentEditor.getValue());
      rememberStructuralValue(previous, preserveDraggedImageReferences(previous, valueRef.current) ?? previous);
      rememberStructuralValue(nextMarkdown, nextMarkdown);
      valueRef.current = nextMarkdown;
      applyingExternalValueRef.current = true;
      editorRef.current?.setValue(nextMarkdown);
      rememberStructuralValue(stripEditorArtifacts(currentEditor.getValue()), nextMarkdown);
      onChangeRef.current(nextMarkdown);
      queueMicrotask(() => {
        applyingExternalValueRef.current = false;
        scheduleDecoration();
      });
    };
    const clearDrag = () => {
      dragging?.source.classList.remove("noosphere-image-dragging", "noosphere-block-dragging");
      dragging = null;
      dropPosition = null;
      dragPointer = null;
      cancelAnimationFrame(dragFrame);
      dragFrame = 0;
      lastDragFrameTime = 0;
      frameBounds.clear();
      dropLine.hidden = true;
      dragPreview?.remove();
      dragPreview = null;
      frameRef.current?.classList.remove("markdown-editor-dragging");
      if (!cancelled) scheduleDecoration();
    };
    const handleDragStart = (event: DragEvent) => {
      const image = event.target instanceof Element ? event.target.closest<HTMLImageElement>("img[data-asset-name]") : null;
      if (!image) return;
      event.stopImmediatePropagation();
      if (readOnlyRef.current || removedNamesRef.current.has(image.dataset.assetName!)) { event.preventDefault(); return; }
      clearDrag();
      const root = image.closest<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      if (!root) { event.preventDefault(); return; }
      const images = Array.from(root.querySelectorAll<HTMLImageElement>("img"));
      let scrollHost: HTMLElement | null = host;
      while (scrollHost && (scrollHost.scrollHeight <= scrollHost.clientHeight
        || !["auto", "scroll"].includes(getComputedStyle(scrollHost).overflowY))) scrollHost = scrollHost.parentElement;
      const scrollContainer = scrollHost ?? document.scrollingElement ?? document.documentElement;
      dragging = {
        kind: "image", index: images.indexOf(image), value: valueRef.current, source: image, root, scrollContainer,
        scrollBounds: scrollHost?.getBoundingClientRect() ?? { top: 0, bottom: window.innerHeight },
        blocks: new Map(), resolve: createImageDropResolver(root, images.indexOf(image), boundsFor), layoutDirty: false,
      };
      image.classList.add("noosphere-image-dragging");
      frameRef.current?.classList.add("markdown-editor-dragging");
      if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.clearData();
        event.dataTransfer.setData("application/x-noosphere-image", `${articleId}:${dragging.index}`);
        if (image.complete && image.naturalWidth && image.naturalHeight) {
          const preview = document.createElement("canvas");
          preview.width = 160;
          preview.height = 100;
          const context = preview.getContext("2d");
          if (context) {
            const scale = Math.min(preview.width / image.naturalWidth, preview.height / image.naturalHeight);
            const width = image.naturalWidth * scale, height = image.naturalHeight * scale;
            context.drawImage(image, (preview.width - width) / 2, (preview.height - height) / 2, width, height);
            preview.className = "noosphere-image-drag-preview";
            preview.setAttribute("aria-hidden", "true");
            document.body.append(preview);
            dragPreview = preview;
            event.dataTransfer.setDragImage(preview, 80, 50);
          }
        }
      }
    };
    const updateDropPosition = (x: number, y: number, fallback?: Element | null) => {
      if (!dragging || readOnlyRef.current) { dropPosition = null; dropLine.hidden = true; return; }
      const { root } = dragging;
      frameBounds.clear();
      if (dragging.layoutDirty) {
        dragging.scrollBounds = dragging.scrollContainer === document.scrollingElement
          ? { top: 0, bottom: window.innerHeight } : boundsFor(dragging.scrollContainer);
        dragging.blocks.clear();
        dragging.resolve = dragging.kind === "image" ? createImageDropResolver(root, dragging.index, boundsFor)
          : blockDropResolver(root, dragging.source, dragging.block!);
        dragging.layoutDirty = false;
      }
      const rootBounds = boundsFor(root);
      if (x < rootBounds.left || x > rootBounds.right || y < rootBounds.top || y > rootBounds.bottom) {
        dropPosition = null; dropLine.hidden = true; return;
      }
      let target = fallback && root.contains(fallback)
        ? fallback.closest<HTMLElement>(".vditor-wysiwyg__block")
          ?? fallback.closest<HTMLElement>("p, li, blockquote, table, hr, h1, h2, h3, h4, h5, h6") : null;
      if (dragging.kind === "block") {
        while (target && target.parentElement !== root) target = target.parentElement;
      }
      const targetBounds = target ? boundsFor(target) : null;
      if (!targetBounds || y < targetBounds.top || y > targetBounds.bottom) {
        const nearestChild = (parent: HTMLElement): HTMLElement | null => {
          let blocks = dragging!.blocks.get(parent);
          if (!blocks) {
            const scrollTop = dragging!.scrollContainer.scrollTop;
            blocks = Array.from(parent.children).flatMap(child => {
              if (!(child instanceof HTMLElement)) return [];
              const bounds = boundsFor(child);
              return bounds.width || bounds.height ? [{ element: child, top: bounds.top + scrollTop, bottom: bounds.bottom + scrollTop }] : [];
            }).sort((a, b) => a.top - b.top);
            dragging!.blocks.set(parent, blocks);
          }
          return blocks[nearestDragBlock(blocks, y + dragging!.scrollContainer.scrollTop)]?.element ?? null;
        };
        target = nearestChild(root);
        if (dragging.kind === "image") while (target && ["UL", "OL"].includes(target.tagName)) target = nearestChild(target);
      }
      if (!root || !target || !root.contains(target)) { dropPosition = null; dropLine.hidden = true; return; }
      const bounds = boundsFor(target);
      const side = (target === root.firstElementChild && target.tagName === "H1") || y >= bounds.top + bounds.height / 2 ? "after" : "before";
      const position = dragging.resolve(target, side);
      if (!position) { dropPosition = null; dropLine.hidden = true; return; }
      if (dragging.block) {
        const snapshot = dragging.block, targetPath = snapshot.mapping.get(position.target);
        const key = targetPath?.join(".") + position.side;
        if (targetPath && !snapshot.validDrops.has(key)) snapshot.validDrops.set(key,
          moveMappedBlockMarkdown(snapshot.markdown, snapshot.sourcePath, targetPath, position.side, snapshot.sourceEnd) !== null);
        if (!targetPath || !snapshot.validDrops.get(key)) { dropPosition = null; dropLine.hidden = true; return; }
      }
      dropPosition = position;
      const frame = boundsFor(frameRef.current!);
      const transform = `translate3d(${position.marker.left - frame.left}px, ${position.marker.top - frame.top - 1.5}px, 0)`;
      if (dropLine.style.transform !== transform) dropLine.style.transform = transform;
      const width = `${position.marker.width}px`;
      if (dropLine.style.width !== width) dropLine.style.width = width;
      dropLine.hidden = false;
    };
    const runDragFrame = (timestamp: number) => {
      dragFrame = 0;
      if (!dragging || !dragPointer || readOnlyRef.current) return;
      updateDropPosition(dragPointer.x, dragPointer.y, dragPointer.fallback);
      const { scrollContainer, scrollBounds } = dragging;
      const velocity = dragScrollVelocity(dragPointer.y, scrollBounds.top, scrollBounds.bottom);
      const elapsed = lastDragFrameTime ? timestamp - lastDragFrameTime : 1000 / 60;
      lastDragFrameTime = timestamp;
      if (velocity) {
        const before = scrollContainer.scrollTop;
        scrollContainer.scrollTop += dragScrollDistance(velocity, elapsed);
        if (scrollContainer.scrollTop !== before) dragFrame = requestAnimationFrame(runDragFrame);
      }
      if (!dragFrame) lastDragFrameTime = 0;
    };
    const scheduleDragFrame = () => {
      if (dragging && dragPointer && !dragFrame) dragFrame = requestAnimationFrame(runDragFrame);
    };
    const handleDragScroll = (event: Event) => {
      if (dragging && event.target !== dragging.scrollContainer) dragging.layoutDirty = true;
      scheduleDragFrame();
    };
    const handleDragOver = (event: DragEvent) => {
      if (!dragging || dragging.kind !== "image" || readOnlyRef.current) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      dragPointer = { x: event.clientX, y: event.clientY, fallback: event.target instanceof Element ? event.target : null };
      if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      scheduleDragFrame();
    };
    const handleDragLeave = (event: DragEvent) => {
      if (!dragging || (event.relatedTarget instanceof Node && host.contains(event.relatedTarget))) return;
      const bounds = host.getBoundingClientRect();
      const viewport = dragging.scrollBounds;
      if (event.clientX >= bounds.left && event.clientX <= bounds.right
        && event.clientY >= Math.max(bounds.top, viewport.top) && event.clientY <= Math.min(bounds.bottom, viewport.bottom)) return;
      dropPosition = null;
      dragPointer = null;
      dropLine.hidden = true;
      cancelAnimationFrame(dragFrame);
      dragFrame = 0;
      lastDragFrameTime = 0;
    };
    const handleDrop = (event: DragEvent) => {
      if (!dragging || dragging.kind !== "image") return;
      event.preventDefault();
      event.stopImmediatePropagation();
      cancelAnimationFrame(dragFrame);
      dragFrame = 0;
      updateDropPosition(event.clientX, event.clientY, event.target instanceof Element ? event.target : null);
      if (dropPosition && dragging.value === valueRef.current) moveImage(dragging.index, dropPosition.target, dropPosition.side);
      clearDrag();
    };
    const blockSnapshot = (source: HTMLElement) => {
      const currentEditor = editorRef.current;
      const root = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      if (!currentEditor || !root || !isMovableArticleBlock(source, root) || readOnlyRef.current) return null;
      const editorValue = stripEditorArtifacts(currentEditor.getValue());
      const live = preserveDraggedImageReferences(editorValue, valueRef.current);
      if (live === null) return null;
      const rendered = preserveDraggedImageReferences(currentEditor.vditor.lute.VditorDOM2Md(currentEditor.vditor.lute.Md2VditorDOM(valueRef.current)), valueRef.current);
      const markdown = rendered === null ? live : reconcileBlockEdits(valueRef.current, rendered, live);
      const { blocks, mapping } = articleBlockMap(root, markdown,
        html => currentEditor.vditor.lute.VditorDOM2Md(html), text => currentEditor.vditor.lute.Md2VditorDOM(text));
      headingFolds.refresh();
      const folded = headingFolds.capture(mapping);
      const path = mapping.get(source);
      const sourceEnd = path?.length === 1 && folded.includes(path[0]) ? headingSectionEnd(blocks, path[0]) : (path?.[0] ?? 0) + 1;
      return !path || !isMovableMarkdownBlock(blocks[path[0]]) ? null
        : { markdown, editorValue, sourcePath: path, mapping, sourceEnd, folded, blocks, selection: captureBlockSelection(root, mapping), validDrops: new Map<string, boolean>() };
    };
    const normalizedBlockTarget = (snapshot: NonNullable<ReturnType<typeof blockSnapshot>>, target: HTMLElement, side: "before" | "after") => {
      const path = snapshot.mapping.get(target);
      if (!path || snapshot.sourcePath.length !== 1 || path.length !== 1) return target;
      const plan = articleBlockMovePlan(snapshot.blocks, snapshot.sourcePath[0], path[0], side, new Set(snapshot.folded));
      return Array.from(snapshot.mapping).find(([, address]) => address.length === 1 && address[0] === plan.target)?.[0] ?? target;
    };
    const blockDropResolver = (root: HTMLElement, source: HTMLElement, snapshot: NonNullable<ReturnType<typeof blockSnapshot>>) => {
      const last = snapshot.sourcePath.length === 1 ? Array.from(snapshot.mapping).find(([, path]) => path.length === 1 && path[0] === snapshot.sourceEnd - 1)?.[0] : source;
      const resolve = createBlockDropResolver(root, source, boundsFor, last ?? source);
      return (target: HTMLElement, side: "before" | "after") => resolve(normalizedBlockTarget(snapshot, target, side), side);
    };
    const blockNeighbor = (source: HTMLElement, side: "before" | "after") => {
      const nodes = headingFolds.isFolded(source) ? headingFolds.sectionNodes(source) : [source];
      let target = side === "before" ? source.previousElementSibling : nodes.at(-1)!.nextElementSibling;
      while (target?.classList.contains("noosphere-fold-hidden")) target = side === "before" ? target.previousElementSibling : target.nextElementSibling;
      const root = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      return root && isMovableArticleBlock(target, root) ? target : null;
    };
    const moveBlock = (source: HTMLElement, target: HTMLElement, side: "before" | "after", snapshot = blockSnapshot(source)) => {
      const currentEditor = editorRef.current;
      const root = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      if (!snapshot || !currentEditor || !root || readOnlyRef.current
        || stripEditorArtifacts(currentEditor.getValue()) !== snapshot.editorValue) return null;
      target = normalizedBlockTarget(snapshot, target, side);
      const sourcePath = snapshot.mapping.get(source), targetPath = snapshot.mapping.get(target);
      const container = source.parentElement;
      if (!sourcePath || !targetPath || !container || target.parentElement !== container) return null;
      const nextMarkdown = moveMappedBlockMarkdown(snapshot.markdown, sourcePath, targetPath, side, snapshot.sourceEnd);
      if (nextMarkdown === null) return null;
      const from = sourcePath.at(-1)!, insertion = targetPath.at(-1)! + Number(side === "after");
      const count = sourcePath.length === 1 ? snapshot.sourceEnd - from : 1;
      const folded = sourcePath.length === 1 ? snapshot.folded.map(index => remapMovedRange(index, from, snapshot.sourceEnd, insertion)) : snapshot.folded;
      rememberFolds(snapshot.editorValue, snapshot.folded);
      rememberFolds(snapshot.markdown, snapshot.folded);
      rememberFolds(nextMarkdown, folded);
      rememberStructuralValue(snapshot.editorValue, snapshot.markdown);
      rememberStructuralValue(nextMarkdown, nextMarkdown);
      currentEditor.vditor.undo?.addToUndoStack(currentEditor.vditor);
      valueRef.current = nextMarkdown;
      applyingExternalValueRef.current = true;
      currentEditor.setValue(nextMarkdown);
      rememberStructuralValue(stripEditorArtifacts(currentEditor.getValue()), nextMarkdown);
      rememberFolds(stripEditorArtifacts(currentEditor.getValue()), folded);
      const surface = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset")!;
      const { mapping } = articleBlockMap(surface, nextMarkdown,
        html => currentEditor.vditor.lute.VditorDOM2Md(html), text => currentEditor.vditor.lute.Md2VditorDOM(text));
      headingFolds.restore(folded, mapping);
      decorateImages();
      const movedPath = [...sourcePath.slice(0, -1), remapMovedRange(from, from, from + count, insertion)];
      const moved = Array.from(mapping).find(([, path]) => path.length === movedPath.length && path.every((index, depth) => index === movedPath[depth]))?.[0];
      surface.focus({ preventScroll: true });
      restoreBlockSelection(snapshot.selection, sourcePath, insertion, mapping, count);
      if (!snapshot.selection && moved) {
        const range = document.createRange();
        range.selectNodeContents(moved);
        range.collapse(true);
        window.getSelection()?.removeAllRanges();
        window.getSelection()?.addRange(range);
      }
      currentEditor.vditor.undo?.addToUndoStack(currentEditor.vditor);
      onChangeRef.current(nextMarkdown);
      queueMicrotask(() => { applyingExternalValueRef.current = false; scheduleDecoration(); });
      return moved ?? null;
    };
    const beginBlockDrag = (source: HTMLElement, point: { x: number; y: number }) => {
      const snapshot = blockSnapshot(source);
      const root = source.parentElement;
      if (!snapshot || !root) return false;
      clearDrag();
      let scrollHost: HTMLElement | null = host;
      while (scrollHost && (scrollHost.scrollHeight <= scrollHost.clientHeight
        || !["auto", "scroll"].includes(getComputedStyle(scrollHost).overflowY))) scrollHost = scrollHost.parentElement;
      const scrollContainer = scrollHost ?? document.scrollingElement ?? document.documentElement;
      dragging = {
        kind: "block", index: Array.from(root.children).indexOf(source), value: valueRef.current, source, root, scrollContainer,
        scrollBounds: scrollHost?.getBoundingClientRect() ?? { top: 0, bottom: window.innerHeight }, blocks: new Map(),
        resolve: blockDropResolver(root, source, snapshot), layoutDirty: false, block: snapshot,
      };
      source.classList.add("noosphere-block-dragging");
      frameRef.current?.classList.add("markdown-editor-dragging");
      dragPointer = { ...point, fallback: null };
      return true;
    };
    const finishBlockDrag = (point: { x: number; y: number }) => {
      if (dragging?.kind !== "block") return;
      updateDropPosition(point.x, point.y);
      const { source, block } = dragging, position = dropPosition;
      clearDrag();
      if (position) {
        const moved = moveBlock(source, position.target, position.side, block);
        if (moved) blockControls?.show(moved);
      }
    };
    const handleImageKeyboard = (event: KeyboardEvent) => {
      if (readOnlyRef.current || !event.altKey || !["ArrowUp", "ArrowDown"].includes(event.key)) return;
      const image = event.target instanceof Element ? event.target.closest<HTMLImageElement>("img[data-asset-name]") : null;
      if (!image || removedNamesRef.current.has(image.dataset.assetName!)) return;
      const source = image.closest("p") ?? image;
      const direction = event.key === "ArrowUp" ? "before" : "after";
      const target = direction === "before" ? source.previousElementSibling : source.nextElementSibling;
      if (!(target instanceof HTMLElement) || (target.tagName === "H1" && direction === "before")) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const index = Array.from(host.querySelectorAll(".vditor-wysiwyg img")).indexOf(image);
      moveImage(index, target, direction);
      requestAnimationFrame(() => host.querySelectorAll<HTMLImageElement>(".vditor-wysiwyg img")[direction === "before" ? Math.max(0, index - Number(target.querySelector("img") !== null)) : index + Number(target.querySelector("img") !== null)]?.focus());
    };
    const decorateImages = () => {
      if (dragging) return;
      headingFolds.refresh();
      const frame = frameRef.current;
      const actionLayer = actionsRef.current;
      if (!frame || !actionLayer) return;
      const frameBounds = frame.getBoundingClientRect();
      const visibleActions = new Set<string>();
      host.querySelectorAll<HTMLImageElement>(".vditor-wysiwyg img").forEach((img, index) => {
        const path = new URL(img.currentSrc || img.src, window.location.origin).pathname;
        if (!path.startsWith(`/api/v1/articles/${encodeURIComponent(articleId)}/assets/`)
            && !path.startsWith(`/api/v1/articles/${encodeURIComponent(articleId)}/removed/`)) return;
        const name = imageName(img.currentSrc || img.src);
        if (!name) return;
        const removed = removedNamesRef.current.has(name);
        img.classList.toggle("noosphere-image-removed", removed);
        img.dataset.assetName = name;
        img.draggable = !readOnlyRef.current && !removed;
        img.tabIndex = readOnlyRef.current || removed ? -1 : 0;
        img.setAttribute("aria-description", t("article.dragImage"));
        const paragraph = img.closest("p");
        const shell = img.closest<HTMLElement>("[data-type='img']")
          ?? (paragraph && !paragraph.textContent?.trim() && paragraph.querySelectorAll("img").length === 1 ? paragraph : img);
        if (!shell) return;
        shell.classList.add("noosphere-image-shell");
        shell.dataset.imageState = removed ? "removed" : "active";
        shell.dataset.noosphereReadonlyImage = "true";
        shell.setAttribute("contenteditable", "false");
        shell.setAttribute("aria-label", t("article.readOnlyImageNamed", { name }));
        if (readOnlyRef.current || shell.getClientRects().length === 0) return;
        const key = `${name}:${index}`;
        visibleActions.add(key);
        let actionGroup = actions.get(key);
        if (!actionGroup) {
          actionGroup = document.createElement("div");
          actionGroup.className = "noosphere-image-actions";
          actionGroup.onclick = handleImageAction;
          for (const actionName of [removed ? "restore" : "delete"] as const) {
            const action = document.createElement("button");
            action.type = "button";
            action.className = "noosphere-image-action";
            action.dataset.action = actionName;
            actionGroup.append(action);
          }
          actionLayer.append(actionGroup);
          actions.set(key, actionGroup);
        }
        const label = removed ? t("article.restoreImage") : t("article.deleteImage");
        actionGroup.dataset.assetName = name;
        actionGroup.dataset.imageIndex = String(index);
        actionGroup.dataset.imageState = removed ? "removed" : "active";
        const stateAction = actionGroup.querySelector<HTMLButtonElement>("[data-action='delete'], [data-action='restore']")!;
        stateAction.dataset.action = removed ? "restore" : "delete";
        stateAction.textContent = label;
        stateAction.setAttribute("aria-label", removed ? t("article.restoreImageNamed", { name }) : t("article.deleteImageNamed", { name }));
        stateAction.title = label;
        const shellBounds = shell.getBoundingClientRect();
        actionGroup.style.top = `${Math.max(0, shellBounds.top - frameBounds.top + 12)}px`;
        actionGroup.style.right = `${Math.max(12, frameBounds.right - shellBounds.right + 12)}px`;
      });
      actions.forEach((action, key) => {
        if (visibleActions.has(key)) return;
        action.remove();
        actions.delete(key);
      });
      blockControls?.refresh();
    };
    const scheduleDecoration = () => {
      if (dragging && readOnlyRef.current) clearDrag();
      if (dragging) {
        dragging.layoutDirty = true;
        scheduleDragFrame();
        return;
      }
      cancelAnimationFrame(decorationFrame);
      decorationFrame = requestAnimationFrame(decorateImages);
    };
    decorateImagesRef.current = scheduleDecoration;
    const articleTextNodes = () => {
      const root = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      if (!root) return { root: null, nodes: [] as Array<{ node: Text; start: number; end: number }>, text: "" };
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          const parent = node.parentElement;
          if (!node.textContent || !parent) return NodeFilter.FILTER_REJECT;
          if (parent.closest(".vditor-copy, textarea, script, style, [aria-hidden='true']")) return NodeFilter.FILTER_REJECT;
          if (parent.closest("[hidden]")) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        }
      });
      const nodes: Array<{ node: Text; start: number; end: number }> = [];
      let text = "";
      let current: Node | null;
      while ((current = walker.nextNode())) {
        const node = current as Text;
        const start = text.length;
        text += node.data;
        nodes.push({ node, start, end: text.length });
      }
      return { root, nodes, text };
    };
    const offsetsToRange = (start: number, end: number, nodes: Array<{ node: Text; start: number; end: number }>) => {
      const first = nodes.find((entry) => start >= entry.start && start < entry.end);
      const last = [...nodes].reverse().find((entry) => end > entry.start && end <= entry.end);
      if (!first || !last || end <= start) return null;
      const range = document.createRange();
      range.setStart(first.node, start - first.start);
      range.setEnd(last.node, end - last.start);
      return range;
    };
    const quoteOffsets = (text: string, annotation: ArticleAnnotation) => {
      const candidates: number[] = [];
      let cursor = 0;
      while (cursor <= text.length - annotation.quote.length) {
        const found = text.indexOf(annotation.quote, cursor);
        if (found < 0) break;
        candidates.push(found);
        cursor = found + Math.max(1, annotation.quote.length);
      }
      if (!candidates.length) return null;
      if (annotation.sourceDigest === annotationPropsRef.current.annotationSourceDigest) {
        const start = candidates[annotation.occurrence];
        return start === undefined ? null : { start, end: start + annotation.quote.length };
      }
      const contextual = candidates.filter((start) => {
        const prefixMatches = !annotation.prefix || text.slice(Math.max(0, start - annotation.prefix.length), start) === annotation.prefix;
        const suffixMatches = !annotation.suffix || text.slice(start + annotation.quote.length, start + annotation.quote.length + annotation.suffix.length) === annotation.suffix;
        return prefixMatches && suffixMatches;
      });
      const safe = contextual.length === 1 ? contextual[0] : candidates.length === 1 ? candidates[0] : undefined;
      return safe === undefined ? null : { start: safe, end: safe + annotation.quote.length };
    };
    const clearHighlight = () => {
      const registry = (CSS as unknown as { highlights?: { delete(name: string): void } }).highlights;
      registry?.delete(highlightName);
    };
    const decorateAnnotations = () => {
      annotationRanges.clear();
      clearHighlight();
      if (!readOnlyRef.current) {
        setAnnotationPreview(null);
        annotationPropsRef.current.onResolvedAnnotationIds?.([]);
        return;
      }
      const model = articleTextNodes();
      if (!model.root) return;
      const ranges: Range[] = [];
      for (const annotation of annotationPropsRef.current.annotations) {
        const offsets = quoteOffsets(model.text, annotation);
        if (!offsets) continue;
        const range = offsetsToRange(offsets.start, offsets.end, model.nodes);
        if (!range) continue;
        annotationRanges.set(annotation.id, range);
        ranges.push(range);
      }
      const registry = (CSS as unknown as { highlights?: { set(name: string, highlight: unknown): void } }).highlights;
      const HighlightConstructor = (window as unknown as { Highlight?: new (...ranges: Range[]) => unknown }).Highlight;
      if (registry && HighlightConstructor && ranges.length) registry.set(highlightName, new HighlightConstructor(...ranges));
      annotationPropsRef.current.onResolvedAnnotationIds?.([...annotationRanges.keys()]);
    };
    const scheduleAnnotationDecoration = () => {
      cancelAnimationFrame(annotationFrame);
      annotationFrame = requestAnimationFrame(decorateAnnotations);
    };
    decorateAnnotationsRef.current = scheduleAnnotationDecoration;
    focusAnnotationRef.current = (annotationId) => {
      scheduleAnnotationDecoration();
      requestAnimationFrame(() => {
        const range = annotationRanges.get(annotationId);
        const element = range?.startContainer.parentElement;
        if (element) headingFolds.reveal(element);
        scheduleDecoration();
        element?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    };
    const selectionOffset = (text: string, quote: string, approximate: number) => {
      const candidates: number[] = [];
      let cursor = 0;
      while (cursor <= text.length - quote.length) {
        const found = text.indexOf(quote, cursor);
        if (found < 0) break;
        candidates.push(found);
        cursor = found + Math.max(1, quote.length);
      }
      return candidates.reduce((closest, candidate) => Math.abs(candidate - approximate) < Math.abs(closest - approximate) ? candidate : closest, candidates[0] ?? -1);
    };
    const handleQuoteSelection = () => {
      if (!readOnlyRef.current) return;
      const selection = window.getSelection();
      const model = articleTextNodes();
      if (!selection?.rangeCount || selection.isCollapsed || !model.root || !selection.anchorNode || !selection.focusNode) {
        annotationPropsRef.current.onSelectQuote?.(null);
        return;
      }
      if (!model.root.contains(selection.anchorNode) || !model.root.contains(selection.focusNode)) return;
      closeAnnotationPreview();
      const range = selection.getRangeAt(0);
      const quote = selection.toString().trim();
      if (!quote) return;
      const before = range.cloneRange();
      before.selectNodeContents(model.root);
      before.setEnd(range.startContainer, range.startOffset);
      const start = selectionOffset(model.text, quote, before.toString().length);
      if (start < 0) return;
      const matchingStarts: number[] = [];
      let cursor = 0;
      while (cursor <= start) {
        const found = model.text.indexOf(quote, cursor);
        if (found < 0 || found > start) break;
        matchingStarts.push(found);
        cursor = found + Math.max(1, quote.length);
      }
      const bounds = range.getBoundingClientRect();
      annotationPropsRef.current.onSelectQuote?.({
        quote,
        prefix: model.text.slice(Math.max(0, start - 96), start),
        suffix: model.text.slice(start + quote.length, start + quote.length + 96),
        occurrence: Math.max(0, matchingStarts.length - 1),
        position: { left: bounds.left + bounds.width / 2, top: bounds.bottom + 10 }
      });
    };
    const annotationAtPoint = (x: number, y: number) => {
      for (const [id, range] of annotationRanges) {
        const line = Array.from(range.getClientRects()).findIndex(rect => rect.width > 0 && x >= rect.left - 2 && x <= rect.right + 2 && y >= rect.top - 2 && y <= rect.bottom + 2);
        if (line >= 0) return { id, range, line };
      }
      return null;
    };
    const handleAnnotationKey = (event: KeyboardEvent) => {
      if (!readOnlyRef.current || (event.key !== "Enter" && event.key !== " ")) return;
      const selection = window.getSelection();
      if (!selection?.isCollapsed || !selection.anchorNode) return;
      for (const [id, range] of annotationRanges) {
        if (!range.isPointInRange(selection.anchorNode, selection.anchorOffset)) continue;
        event.preventDefault();
        setAnnotationPreview({ id, range, line: 0 });
        return;
      }
    };
    const handleAnnotationClick = (event: MouseEvent) => {
      if (!readOnlyRef.current || window.getSelection()?.toString()) return;
      const anchor = annotationAtPoint(event.clientX, event.clientY);
      if (!anchor) return;
      event.preventDefault();
      setAnnotationPreview(current => current?.id === anchor.id ? null : anchor);
    };
    const keepRenderedBlocksVisible = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const copyButton = target.closest<HTMLElement>(".vditor-copy span");
      if (copyButton) {
        event.preventDefault();
        event.stopPropagation();
        const textarea = copyButton.parentElement?.querySelector<HTMLTextAreaElement>("textarea");
        if (textarea) {
          void copyText(textarea.value).then(() => copyButton.setAttribute("aria-label", t("article.codeCopied")));
        }
        return;
      }
      if (target.closest("[data-noosphere-readonly-image='true']")) {
        const anchor = target.closest<HTMLAnchorElement>("a");
        if (!anchor) {
          event.preventDefault();
          event.stopPropagation();
        }
        return;
      }
      if (target.closest(".vditor-wysiwyg__preview")) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    const handleImageAction = (event: MouseEvent) => {
      const target = event.target;
      if (!(target instanceof Element)) return;
      const imageAction = target.closest<HTMLButtonElement>(".noosphere-image-action");
      if (imageAction) {
        event.preventDefault();
        event.stopPropagation();
        const actionGroup = imageAction.closest<HTMLElement>(".noosphere-image-actions");
        const name = actionGroup?.dataset.assetName;
        if (!name) return;
        if (imageAction.dataset.action === "restore") imageActionsRef.current.onRestoreImage?.(name);
        else if (imageAction.dataset.action === "delete") imageActionsRef.current.onDeleteImage?.(name);
      }
    };
    const isIgnorableEditorNode = (node: Node) => {
      if (node.nodeType === Node.TEXT_NODE) return /^[\s\u200B\uFEFF]*$/.test(node.textContent ?? "");
      return node instanceof HTMLElement && ["BR", "WBR"].includes(node.tagName);
    };
    const adjacentNode = (selection: Selection, direction: "backward" | "forward", root: HTMLElement) => {
      let node: Node | null = selection.anchorNode;
      let offset = selection.anchorOffset;
      if (!node) return null;
      if (node.nodeType === Node.TEXT_NODE) {
        const textLength = node.textContent?.length ?? 0;
        const remainingText = direction === "backward"
          ? node.textContent?.slice(0, offset)
          : node.textContent?.slice(offset, textLength);
        if (remainingText && !/^[\s\u200B\uFEFF]*$/.test(remainingText)) return null;
        const parent: ParentNode | null = node.parentNode;
        if (!parent) return null;
        offset = Array.from(parent.childNodes).findIndex((child) => child === node) + (direction === "forward" ? 1 : 0);
        node = parent as Node;
      }
      while (node && node !== root) {
        const children = Array.from(node.childNodes);
        let candidate = direction === "backward" ? children[offset - 1] : children[offset];
        while (candidate && isIgnorableEditorNode(candidate)) {
          offset += direction === "backward" ? -1 : 1;
          candidate = direction === "backward" ? children[offset - 1] : children[offset];
        }
        if (candidate) return candidate;
        const parent: ParentNode | null = node.parentNode;
        if (!parent) return null;
        offset = Array.from(parent.childNodes).findIndex((child) => child === node) + (direction === "forward" ? 1 : 0);
        node = parent as Node;
      }
      return null;
    };
    const isProtectedImageNode = (node: Node | null) => {
      const element = node instanceof Element ? node : node?.parentElement;
      return Boolean(element?.matches("[data-noosphere-readonly-image='true']")
        || element?.closest("[data-noosphere-readonly-image='true']")
        || element?.querySelector("[data-noosphere-readonly-image='true']"));
    };
    const blockBoundaryImage = (selection: Selection, direction: "backward" | "forward", root: HTMLElement) => {
      const range = selection.getRangeAt(0);
      const anchorElement = selection.anchorNode instanceof Element ? selection.anchorNode : selection.anchorNode?.parentElement;
      const block = anchorElement?.closest<HTMLElement>("[data-block='0']");
      if (!block || !root.contains(block) || isProtectedImageNode(block)) return isProtectedImageNode(block ?? null);
      const boundary = document.createRange();
      boundary.selectNodeContents(block);
      try {
        if (direction === "backward") boundary.setEnd(range.startContainer, range.startOffset);
        else boundary.setStart(range.endContainer, range.endOffset);
      } catch {
        return false;
      }
      if (!/^[\s\u200B\uFEFF]*$/.test(boundary.toString())) return false;
      const sibling = direction === "backward" ? block.previousElementSibling : block.nextElementSibling;
      return isProtectedImageNode(sibling);
    };
    const shouldPreventAtomicImageDeletion = (direction: "backward" | "forward") => {
      const editableSurface = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      const selection = window.getSelection();
      if (!editableSurface || !selection?.rangeCount || !selection.anchorNode || !editableSurface.contains(selection.anchorNode)) return false;
      const range = selection.getRangeAt(0);
      if (!selection.isCollapsed) {
        return Array.from(editableSurface.querySelectorAll("[data-noosphere-readonly-image='true']"))
          .some((imageBlock) => range.intersectsNode(imageBlock));
      }
      return blockBoundaryImage(selection, direction, editableSurface)
        || isProtectedImageNode(adjacentNode(selection, direction, editableSurface));
    };
    const cancelProtectedImageMutation = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    };
    const preventAtomicImageDeletion = (event: KeyboardEvent) => {
      if (readOnlyRef.current || (event.key !== "Backspace" && event.key !== "Delete")) return;
      const direction = event.key === "Backspace" ? "backward" : "forward";
      if (shouldPreventAtomicImageDeletion(direction)) cancelProtectedImageMutation(event);
    };
    const preventAtomicImageBeforeInput = (event: InputEvent) => {
      if (readOnlyRef.current) return;
      if (event.inputType === "deleteContentBackward" && shouldPreventAtomicImageDeletion("backward")) cancelProtectedImageMutation(event);
      if (event.inputType === "deleteContentForward" && shouldPreventAtomicImageDeletion("forward")) cancelProtectedImageMutation(event);
    };
    const preventAtomicImageCut = (event: ClipboardEvent) => {
      if (readOnlyRef.current) return;
      const editableSurface = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      const selection = window.getSelection();
      if (!editableSurface || !selection?.rangeCount || selection.isCollapsed) return;
      const range = selection.getRangeAt(0);
      if (Array.from(editableSurface.querySelectorAll("[data-noosphere-readonly-image='true']")).some((imageBlock) => range.intersectsNode(imageBlock))) {
        cancelProtectedImageMutation(event);
      }
    };
    host.addEventListener("click", keepRenderedBlocksVisible, true);
    host.addEventListener("click", handleAnnotationClick);
    host.addEventListener("keyup", handleAnnotationKey);
    host.addEventListener("mouseup", handleQuoteSelection);
    host.addEventListener("keyup", handleQuoteSelection);
    host.addEventListener("keydown", preventAtomicImageDeletion, true);
    host.addEventListener("beforeinput", preventAtomicImageBeforeInput, true);
    host.addEventListener("cut", preventAtomicImageCut, true);
    host.addEventListener("dragstart", handleDragStart, true);
    host.addEventListener("dragover", handleDragOver, true);
    host.addEventListener("dragleave", handleDragLeave, true);
    host.addEventListener("drop", handleDrop, true);
    host.addEventListener("dragend", clearDrag, true);
    host.addEventListener("keydown", handleImageKeyboard, true);
    window.addEventListener("scroll", handleDragScroll, true);
    if (frameRef.current && actionsRef.current) blockControls = installBlockControls({
      host, frame: frameRef.current, layer: actionsRef.current,
      root: () => host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset"),
      readOnly: () => readOnlyRef.current, isDragging: () => Boolean(dragging),
      labels: { handle: t("article.moveBlock"), up: t("article.moveBlockUp"), down: t("article.moveBlockDown"),
        wholeList: t("article.moveWholeList"), listItem: t("article.moveListItem"),
        heading: t("article.moveHeading"), section: t("article.moveSection"), fold: t("article.foldHeading"), unfold: t("article.unfoldHeading") },
      neighbor: blockNeighbor,
      canFold: headingFolds.canFold, isFolded: headingFolds.isFolded,
      toggleFold: source => {
        const snapshot = blockSnapshot(source);
        if (!snapshot || !headingFolds.toggle(source)) return;
        const folded = headingFolds.capture(snapshot.mapping);
        rememberFolds(snapshot.markdown, folded);
        rememberFolds(snapshot.editorValue, folded);
        scheduleDecoration();
      },
      begin: beginBlockDrag,
      update: (point) => { dragPointer = { ...point, fallback: null }; scheduleDragFrame(); },
      finish: finishBlockDrag, cancel: clearDrag,
      move: (source, side) => {
        const target = blockNeighbor(source, side);
        if (!target) return null;
        const moved = moveBlock(source, target, side);
        moved?.scrollIntoView({ block: "nearest" });
        return moved;
      }
    });

    const revealBlock = (event: Event) => {
      if (event.target instanceof Element) { headingFolds.reveal(event.target); scheduleDecoration(); }
    };
    host.addEventListener("noosphere-reveal-block", revealBlock);

    async function mountEditor() {
      if (i18n.resolvedLanguage === "zh") {
        await import("vditor/dist/js/i18n/zh_CN.js");
      } else {
        await import("vditor/dist/js/i18n/en_US.js");
      }
      if (cancelled || !hostRef.current) return;
      const i18nBundle = { ...window.VditorI18n };
      editor = new Vditor(hostRef.current, {
        value: valueRef.current,
        mode: "wysiwyg",
        lang: i18n.resolvedLanguage === "zh" ? "zh_CN" : "en_US",
        i18n: i18nBundle,
        cdn: "/app/vditor",
        theme: resolvedThemeRef.current === "dark" ? "dark" : "classic",
        height: "auto",
        minHeight: 620,
        cache: { enable: false },
        counter: { enable: false },
        toolbarConfig: { hide: true },
        toolbar: [],
        customWysiwygToolbar: (type, element) => {
          if (!STRUCTURAL_POPOVER_TYPES.has(type)) return;
          element.replaceChildren();
          element.classList.add("vditor-panel--none");
          element.setAttribute("aria-hidden", "true");
        },
        preview: {
          delay: 180,
          hljs: { enable: true, lineNumber: true, style: resolvedThemeRef.current === "dark" ? "native" : "github" },
          theme: {
            current: resolvedThemeRef.current === "dark" ? "dark" : "light",
            path: "/app/vditor/dist/css/content-theme"
          },
          markdown: {
            gfmAutoLink: true,
            footnotes: true,
            mark: true,
            sanitize: true,
            linkBase: `/api/v1/articles/${encodeURIComponent(articleId)}/`
          }
        },
        link: { isOpen: false },
        image: { isPreview: false },
        input: (markdown) => {
          if (readOnlyRef.current || applyingExternalValueRef.current || restoringImageStructureRef.current) return;
          const cleaned = stripEditorArtifacts(markdown);
          const candidate = structuralHistoryRef.current.get(markdownStateKey(cleaned)) ?? cleaned;
          if (!hasSameImageStructure(candidate, valueRef.current) && !structuralHistoryRef.current.has(markdownStateKey(cleaned))) {
            restoringImageStructureRef.current = true;
            queueMicrotask(() => {
              editorRef.current?.setValue(valueRef.current);
              restoringImageStructureRef.current = false;
              scheduleDecoration();
            });
            return;
          }
          valueRef.current = candidate;
          const folded = foldHistory.get(markdownStateKey(cleaned)) ?? foldHistory.get(markdownStateKey(candidate));
          const root = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
          if (folded && root && editorRef.current) {
            const { mapping } = articleBlockMap(root, candidate,
              html => editorRef.current!.vditor.lute.VditorDOM2Md(html), text => editorRef.current!.vditor.lute.Md2VditorDOM(text));
            headingFolds.restore(folded, mapping);
          } else headingFolds.refresh();
          onChangeRef.current(candidate);
        },
        after: () => {
          if (cancelled) {
            editor?.destroy();
            return;
          }
          editorRef.current = editor;
          editor?.setTheme(
            resolvedThemeRef.current === "dark" ? "dark" : "classic",
            resolvedThemeRef.current === "dark" ? "dark" : "light",
            resolvedThemeRef.current === "dark" ? "native" : "github",
            "/app/vditor/dist/css/content-theme"
          );
          if (readOnlyRef.current) editor?.disabled();
          const editableSurface = hostRef.current?.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
          editableSurface?.setAttribute("contenteditable", readOnlyRef.current ? "false" : "true");
          editableSurface?.setAttribute("aria-readonly", String(readOnlyRef.current));
          scheduleDecoration();
          scheduleAnnotationDecoration();
          observer = new MutationObserver(() => {
            scheduleDecoration();
            scheduleAnnotationDecoration();
          });
          observer.observe(host, { childList: true, subtree: true, attributes: true, attributeFilter: ["src"] });
          resizeObserver = new ResizeObserver(scheduleDecoration);
          resizeObserver.observe(host);
        }
      });
    }

    host.addEventListener("load", scheduleDecoration, true);
    window.addEventListener("resize", scheduleDecoration);
    void mountEditor();
    return () => {
      cancelled = true;
      host.removeEventListener("click", keepRenderedBlocksVisible, true);
      host.removeEventListener("click", handleAnnotationClick);
      host.removeEventListener("keyup", handleAnnotationKey);
      closeAnnotationPreview();
      host.removeEventListener("mouseup", handleQuoteSelection);
      host.removeEventListener("keyup", handleQuoteSelection);
      host.removeEventListener("keydown", preventAtomicImageDeletion, true);
      host.removeEventListener("beforeinput", preventAtomicImageBeforeInput, true);
      host.removeEventListener("cut", preventAtomicImageCut, true);
      host.removeEventListener("dragstart", handleDragStart, true);
      host.removeEventListener("dragover", handleDragOver, true);
      host.removeEventListener("dragleave", handleDragLeave, true);
      host.removeEventListener("drop", handleDrop, true);
      host.removeEventListener("dragend", clearDrag, true);
      host.removeEventListener("keydown", handleImageKeyboard, true);
      window.removeEventListener("scroll", handleDragScroll, true);
      blockControls?.destroy();
      blockControls = null;
      headingFolds.destroy();
      host.removeEventListener("noosphere-reveal-block", revealBlock);
      clearDrag();
      dropLine.remove();
      host.removeEventListener("load", scheduleDecoration, true);
      window.removeEventListener("resize", scheduleDecoration);
      cancelAnimationFrame(decorationFrame);
      cancelAnimationFrame(annotationFrame);
      clearHighlight();
      observer?.disconnect();
      resizeObserver?.disconnect();
      actions.forEach((action) => action.remove());
      actions.clear();
      editor?.destroy();
      editorRef.current = null;
      decorateImagesRef.current = () => undefined;
      decorateAnnotationsRef.current = () => undefined;
      focusAnnotationRef.current = () => undefined;
    };
  }, [articleId, i18n.resolvedLanguage, t]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (readOnly) editor.disabled();
    else editor.enable();
    const editableSurface = hostRef.current?.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
    editableSurface?.setAttribute("contenteditable", readOnly ? "false" : "true");
    editableSurface?.setAttribute("aria-readonly", String(readOnly));
    hostRef.current?.querySelectorAll<HTMLElement>(".vditor-wysiwyg > .vditor-panel").forEach((panel) => {
      panel.style.display = "none";
    });
    decorateImagesRef.current();
    decorateAnnotationsRef.current();
  }, [readOnly]);

  useEffect(() => {
    editorRef.current?.setTheme(
      resolvedTheme === "dark" ? "dark" : "classic",
      resolvedTheme === "dark" ? "dark" : "light",
      resolvedTheme === "dark" ? "native" : "github",
      "/app/vditor/dist/css/content-theme"
    );
  }, [resolvedTheme]);

  const annotationKey = annotations.map((annotation) => `${annotation.id}:${annotation.updatedAt}:${annotation.sourceDigest}`).join("\n");
  useEffect(() => {
    decorateAnnotationsRef.current();
  }, [annotationKey, annotationSourceDigest]);

  useEffect(() => {
    if (focusAnnotationRequest) focusAnnotationRef.current(focusAnnotationRequest.id);
  }, [focusAnnotationRequest]);

  const removedAssetKey = [...removedAssetNames].sort().join("\n");
  useEffect(() => {
    removedNamesRef.current = new Set(removedAssetNames);
    decorateImagesRef.current();
  }, [removedAssetKey]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const current = stripEditorArtifacts(editor.getValue());
    if (current !== value && structuralHistoryRef.current.get(markdownStateKey(current)) !== value) {
      applyingExternalValueRef.current = true;
      editor.setValue(value);
      queueMicrotask(() => {
        applyingExternalValueRef.current = false;
        decorateImagesRef.current();
      });
    }
  }, [value]);

  return (
    <div className={`markdown-editor-frame${readOnly ? " markdown-editor-readonly" : ""}${showRemovedImages ? "" : " markdown-editor-hide-removed"}`} ref={frameRef}>
      <div className="markdown-editor" ref={hostRef} aria-label={t("article.editorLabel")} />
      <div className="noosphere-image-actions-layer" ref={actionsRef} aria-hidden={readOnly} />
      {readOnly && annotationPreview && annotations.find(annotation => annotation.id === annotationPreview.id) && <QuoteAnnotationPreview
        annotation={annotations.find(annotation => annotation.id === annotationPreview.id)!} anchor={annotationPreview}
        onClose={closeAnnotationPreview}
        onEdit={() => { closeAnnotationPreview(); onOpenAnnotation?.(annotationPreview.id); }} />}
    </div>
  );
}
