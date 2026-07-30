import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import Vditor from "vditor";
import "vditor/dist/index.css";
import "./MarkdownEditor.css";
import { useTheme } from "../theme";

interface MarkdownEditorProps {
  articleId: string;
  value: string;
  onChange: (value: string) => void;
  readOnly: boolean;
  removedAssetNames?: string[];
  showRemovedImages?: boolean;
  onDeleteImage?: (assetName: string) => void;
  onRestoreImage?: (assetName: string) => void;
}

const EDITOR_IMAGE_ACTION_RE = /[ \t]*<button\b[^>]*\bclass\s*=\s*["'][^"']*\bnoosphere-image-action\b[^"']*["'][^>]*>.*?<\/button>[ \t]*\n?/gis;
const MARKDOWN_IMAGE_TARGET_RE = /!\[[^\]\n]*]\(\s*(?:<([^>\n]+)>|([^\s)\n]+))[^)\n]*\)|<img\b[^>]*\bsrc\s*=\s*["']([^"']+)["'][^>]*>/gi;

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

export function MarkdownEditor({ articleId, value, onChange, readOnly, removedAssetNames = [], showRemovedImages = true, onDeleteImage, onRestoreImage }: MarkdownEditorProps) {
  const frameRef = useRef<HTMLDivElement>(null);
  const hostRef = useRef<HTMLDivElement>(null);
  const actionsRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<Vditor | null>(null);
  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  const removedNamesRef = useRef(new Set(removedAssetNames));
  const decorateImagesRef = useRef<() => void>(() => undefined);
  const imageActionsRef = useRef({ onDeleteImage, onRestoreImage });
  const restoringImageStructureRef = useRef(false);
  const applyingExternalValueRef = useRef(false);
  const { i18n, t } = useTranslation();
  const { resolvedTheme } = useTheme();

  onChangeRef.current = onChange;
  valueRef.current = value;
  removedNamesRef.current = new Set(removedAssetNames);
  imageActionsRef.current = { onDeleteImage, onRestoreImage };

  useEffect(() => {
    if (!hostRef.current) return;
    const host = hostRef.current;
    let cancelled = false;
    let editor: Vditor | null = null;
    let observer: MutationObserver | null = null;
    let resizeObserver: ResizeObserver | null = null;
    let decorationFrame = 0;
    const actions = new Map<string, HTMLButtonElement>();
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
        if (readOnly || shell.getClientRects().length === 0) return;
        const key = `${name}:${index}`;
        visibleActions.add(key);
        let action = actions.get(key);
        if (!action) {
          action = document.createElement("button");
          action.type = "button";
          action.className = "noosphere-image-action";
          actionLayer.append(action);
          actions.set(key, action);
        }
        const label = removed ? t("article.restoreImage") : t("article.deleteImage");
        action.dataset.action = removed ? "restore" : "delete";
        action.dataset.assetName = name;
        action.dataset.imageState = removed ? "removed" : "active";
        if (action.textContent !== label) action.textContent = label;
        action.setAttribute("aria-label", removed ? t("article.restoreImageNamed", { name }) : t("article.deleteImageNamed", { name }));
        const shellBounds = shell.getBoundingClientRect();
        action.style.top = `${Math.max(0, shellBounds.top - frameBounds.top + 12)}px`;
        action.style.right = `${Math.max(12, frameBounds.right - shellBounds.right + 12)}px`;
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
        const name = imageAction.dataset.assetName;
        if (!name) return;
        if (imageAction.dataset.action === "restore") imageActionsRef.current.onRestoreImage?.(name);
        else imageActionsRef.current.onDeleteImage?.(name);
      }
    };
    const adjacentNode = (selection: Selection, direction: "backward" | "forward", root: HTMLElement) => {
      let node: Node | null = selection.anchorNode;
      let offset = selection.anchorOffset;
      if (!node) return null;
      if (node.nodeType === Node.TEXT_NODE) {
        const textLength = node.textContent?.length ?? 0;
        if ((direction === "backward" && offset > 0) || (direction === "forward" && offset < textLength)) return null;
        const parent: ParentNode | null = node.parentNode;
        if (!parent) return null;
        offset = Array.from(parent.childNodes).findIndex((child) => child === node) + (direction === "forward" ? 1 : 0);
        node = parent as Node;
      }
      while (node && node !== root) {
        const children = Array.from(node.childNodes);
        const candidate = direction === "backward" ? children[offset - 1] : children[offset];
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
        || element?.closest("[data-noosphere-readonly-image='true']"));
    };
    const preventAtomicImageDeletion = (event: KeyboardEvent) => {
      if (readOnly || (event.key !== "Backspace" && event.key !== "Delete")) return;
      const editableSurface = host.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
      const selection = window.getSelection();
      if (!editableSurface || !selection?.rangeCount || !selection.anchorNode || !editableSurface.contains(selection.anchorNode)) return;
      const range = selection.getRangeAt(0);
      if (!selection.isCollapsed) {
        const includesImage = Array.from(editableSurface.querySelectorAll("[data-noosphere-readonly-image='true']"))
          .some((imageBlock) => range.intersectsNode(imageBlock));
        if (includesImage) event.preventDefault();
        return;
      }
      const direction = event.key === "Backspace" ? "backward" : "forward";
      if (isProtectedImageNode(adjacentNode(selection, direction, editableSurface))) event.preventDefault();
    };
    host.addEventListener("click", keepRenderedBlocksVisible, true);
    host.addEventListener("keydown", preventAtomicImageDeletion, true);
    actionsRef.current?.addEventListener("click", handleImageAction);

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
        theme: resolvedTheme === "dark" ? "dark" : "classic",
        height: "auto",
        minHeight: 620,
        cache: { enable: false },
        counter: { enable: false },
        toolbarConfig: { hide: true },
        toolbar: [],
        customWysiwygToolbar: () => undefined,
        preview: {
          delay: 180,
          hljs: { enable: true, lineNumber: true, style: resolvedTheme === "dark" ? "native" : "github" },
          theme: {
            current: resolvedTheme === "dark" ? "dark" : "light",
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
          if (readOnly || applyingExternalValueRef.current || restoringImageStructureRef.current) return;
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
            resolvedTheme === "dark" ? "dark" : "classic",
            resolvedTheme === "dark" ? "dark" : "light",
            resolvedTheme === "dark" ? "native" : "github",
            "/app/vditor/dist/css/content-theme"
          );
          if (readOnly) editor?.disabled();
          const editableSurface = hostRef.current?.querySelector<HTMLElement>(".vditor-wysiwyg .vditor-reset");
          editableSurface?.setAttribute("contenteditable", readOnly ? "false" : "true");
          editableSurface?.setAttribute("aria-readonly", String(readOnly));
          scheduleDecoration();
          observer = new MutationObserver(scheduleDecoration);
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
      host.removeEventListener("keydown", preventAtomicImageDeletion, true);
      host.removeEventListener("load", scheduleDecoration, true);
      actionsRef.current?.removeEventListener("click", handleImageAction);
      window.removeEventListener("resize", scheduleDecoration);
      cancelAnimationFrame(decorationFrame);
      observer?.disconnect();
      resizeObserver?.disconnect();
      actions.forEach((action) => action.remove());
      actions.clear();
      editor?.destroy();
      editorRef.current = null;
      decorateImagesRef.current = () => undefined;
    };
  }, [articleId, i18n.resolvedLanguage, readOnly, resolvedTheme, t]);

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
