import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import Vditor from "vditor";
import "vditor/dist/index.css";
import "./MarkdownEditor.css";
import { useTheme } from "../theme";
import type { ArticleAnnotation, QuoteAnchorDraft } from "../types";

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

function imageTargetName(source: string) {
  const cleanSource = source.split(/[?#]/, 1)[0];
  try {
    return decodeURIComponent(cleanSource.split("/").pop() ?? "");
  } catch {
    return cleanSource.split("/").pop() ?? "";
  }
}

function moveImageBlockInMarkdown(markdown: string, assetName: string, imageIndex: number, direction: "up" | "down") {
  const segments = markdown.split(/(\n[ \t]*\n(?:[ \t]*\n)*)/);
  let currentImageIndex = 0;
  let targetSegmentIndex = -1;
  for (let segmentIndex = 0; segmentIndex < segments.length; segmentIndex += 2) {
    const segment = segments[segmentIndex];
    for (const match of stripEditorArtifacts(segment).matchAll(MARKDOWN_IMAGE_TARGET_RE)) {
      const source = match[1] || match[2] || match[3] || "";
      if (currentImageIndex === imageIndex && imageTargetName(source) === assetName && match[0].trim() === segment.trim()) {
        targetSegmentIndex = segmentIndex;
        break;
      }
      currentImageIndex += 1;
    }
    if (targetSegmentIndex >= 0) break;
  }
  const siblingSegmentIndex = targetSegmentIndex + (direction === "up" ? -2 : 2);
  if (targetSegmentIndex < 0 || siblingSegmentIndex < 0 || siblingSegmentIndex >= segments.length) return null;
  [segments[targetSegmentIndex], segments[siblingSegmentIndex]] = [segments[siblingSegmentIndex], segments[targetSegmentIndex]];
  return segments.join("");
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
  const imageActionsRef = useRef({ onDeleteImage, onRestoreImage });
  const annotationPropsRef = useRef({ annotations, annotationSourceDigest, onSelectQuote, onOpenAnnotation, onResolvedAnnotationIds });
  const restoringImageStructureRef = useRef(false);
  const applyingExternalValueRef = useRef(false);
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
    let cancelled = false;
    let editor: Vditor | null = null;
    let observer: MutationObserver | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let decorationFrame = 0;
    let annotationFrame = 0;
    const annotationRanges = new Map<string, Range>();
    const highlightName = "noosphere-article-annotations";
    const actions = new Map<string, HTMLDivElement>();
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
    const editableImageBlock = (shell: HTMLElement) => shell.closest<HTMLElement>("[data-block='0']") ?? shell;
    const moveImageBlock = (name: string, index: number, direction: "up" | "down") => {
      if (readOnlyRef.current) return;
      const nextMarkdown = moveImageBlockInMarkdown(valueRef.current, name, index, direction);
      if (!nextMarkdown) return;
      valueRef.current = nextMarkdown;
      applyingExternalValueRef.current = true;
      editorRef.current?.setValue(nextMarkdown);
      onChangeRef.current(nextMarkdown);
      queueMicrotask(() => {
        applyingExternalValueRef.current = false;
        scheduleDecoration();
      });
    };
    const decorateImages = () => {
      const frame = frameRef.current;
      const actionLayer = actionsRef.current;
      if (!frame || !actionLayer) return;
      const frameBounds = frame.getBoundingClientRect();
      const visibleActions = new Set<string>();
      host.querySelectorAll<HTMLImageElement>(".vditor-wysiwyg img").forEach((img, index) => {
        const name = imageName(img.currentSrc || img.src);
        if (!name) return;
        const removed = removedNamesRef.current.has(name);
        img.classList.toggle("noosphere-image-removed", removed);
        img.dataset.assetName = name;
        img.draggable = false;
        const shell = (img.closest<HTMLElement>("[data-type='img']") ?? img.parentElement);
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
          for (const actionName of ["move-up", "move-down", removed ? "restore" : "delete"] as const) {
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
        const moveUp = actionGroup.querySelector<HTMLButtonElement>("[data-action='move-up']")!;
        const moveDown = actionGroup.querySelector<HTMLButtonElement>("[data-action='move-down']")!;
        const stateAction = actionGroup.querySelector<HTMLButtonElement>("[data-action='delete'], [data-action='restore']")!;
        stateAction.dataset.action = removed ? "restore" : "delete";
        moveUp.textContent = "↑";
        moveDown.textContent = "↓";
        moveUp.setAttribute("aria-label", t("article.moveImageUpNamed", { name }));
        moveDown.setAttribute("aria-label", t("article.moveImageDownNamed", { name }));
        moveUp.title = t("article.moveImageUp");
        moveDown.title = t("article.moveImageDown");
        stateAction.textContent = label;
        stateAction.setAttribute("aria-label", removed ? t("article.restoreImageNamed", { name }) : t("article.deleteImageNamed", { name }));
        stateAction.title = label;
        const block = editableImageBlock(shell);
        moveUp.disabled = removed || !block.previousElementSibling;
        moveDown.disabled = removed || !block.nextElementSibling;
        const shellBounds = shell.getBoundingClientRect();
        actionGroup.style.top = `${Math.max(0, shellBounds.top - frameBounds.top + 12)}px`;
        actionGroup.style.right = `${Math.max(12, frameBounds.right - shellBounds.right + 12)}px`;
      });
      actions.forEach((action, key) => {
        if (visibleActions.has(key)) return;
        action.remove();
        actions.delete(key);
      });
    };
    const scheduleDecoration = () => {
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
    const handleAnnotationClick = (event: MouseEvent) => {
      if (!readOnlyRef.current || window.getSelection()?.toString()) return;
      const documentWithCaret = document as Document & { caretRangeFromPoint?: (x: number, y: number) => Range | null };
      const point = documentWithCaret.caretRangeFromPoint?.(event.clientX, event.clientY);
      if (!point) return;
      for (const [annotationId, range] of annotationRanges) {
        if (!range.isPointInRange(point.startContainer, point.startOffset)) continue;
        event.preventDefault();
        annotationPropsRef.current.onOpenAnnotation?.(annotationId);
        break;
      }
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
        const index = Number(actionGroup?.dataset.imageIndex ?? -1);
        if (!name) return;
        if (imageAction.dataset.action === "move-up" && index >= 0) moveImageBlock(name, index, "up");
        else if (imageAction.dataset.action === "move-down" && index >= 0) moveImageBlock(name, index, "down");
        else if (imageAction.dataset.action === "restore") imageActionsRef.current.onRestoreImage?.(name);
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
    host.addEventListener("mouseup", handleQuoteSelection);
    host.addEventListener("keyup", handleQuoteSelection);
    host.addEventListener("keydown", preventAtomicImageDeletion, true);
    host.addEventListener("beforeinput", preventAtomicImageBeforeInput, true);
    host.addEventListener("cut", preventAtomicImageCut, true);

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
          if (!hasSameImageStructure(cleaned, valueRef.current)) {
            restoringImageStructureRef.current = true;
            queueMicrotask(() => {
              editorRef.current?.setValue(valueRef.current);
              restoringImageStructureRef.current = false;
              scheduleDecoration();
            });
            return;
          }
          onChangeRef.current(cleaned);
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
      host.removeEventListener("mouseup", handleQuoteSelection);
      host.removeEventListener("keyup", handleQuoteSelection);
      host.removeEventListener("keydown", preventAtomicImageDeletion, true);
      host.removeEventListener("beforeinput", preventAtomicImageBeforeInput, true);
      host.removeEventListener("cut", preventAtomicImageCut, true);
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
    if (stripEditorArtifacts(editor.getValue()) !== value) {
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
    </div>
  );
}
