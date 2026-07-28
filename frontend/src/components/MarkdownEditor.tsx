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
  onDeleteImage?: (assetName: string) => void;
  onRestoreImage?: (assetName: string) => void;
}

const EDITOR_IMAGE_ACTION_RE = /[ \t]*<button\b[^>]*\bclass\s*=\s*["'][^"']*\bnoosphere-image-action\b[^"']*["'][^>]*>.*?<\/button>[ \t]*\n?/gis;

function stripEditorArtifacts(markdown: string) {
  return markdown.replace(EDITOR_IMAGE_ACTION_RE, "");
}

export function MarkdownEditor({ articleId, value, onChange, readOnly, removedAssetNames = [], onDeleteImage, onRestoreImage }: MarkdownEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<Vditor | null>(null);
  const onChangeRef = useRef(onChange);
  const valueRef = useRef(value);
  const removedNamesRef = useRef(new Set(removedAssetNames));
  const imageActionsRef = useRef({ onDeleteImage, onRestoreImage });
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
      host.querySelectorAll<HTMLImageElement>(".vditor-wysiwyg img").forEach((img) => {
        const name = imageName(img.currentSrc || img.src);
        if (!name) return;
        const removed = removedNamesRef.current.has(name) || img.src.includes("/removed/");
        img.classList.toggle("noosphere-image-removed", removed);
        img.dataset.assetName = name;
        const shell = (img.closest<HTMLElement>("[data-type='img']") ?? img.parentElement);
        if (!shell) return;
        shell.classList.add("noosphere-image-shell");
        shell.dataset.imageState = removed ? "removed" : "active";
        let action = shell.querySelector<HTMLButtonElement>(".noosphere-image-action");
        if (readOnly) {
          action?.remove();
          return;
        }
        if (!action) {
          action = document.createElement("button");
          action.type = "button";
          action.className = "noosphere-image-action";
          shell.append(action);
        }
        const label = removed ? t("article.restoreImage") : t("article.deleteImage");
        action.dataset.action = removed ? "restore" : "delete";
        action.dataset.assetName = name;
        if (action.textContent !== label) action.textContent = label;
        action.setAttribute("aria-label", removed ? t("article.restoreImageNamed", { name }) : t("article.deleteImageNamed", { name }));
      });
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
      const imageAction = target.closest<HTMLButtonElement>(".noosphere-image-action");
      if (imageAction) {
        event.preventDefault();
        event.stopPropagation();
        const name = imageAction.dataset.assetName;
        if (!name) return;
        if (imageAction.dataset.action === "restore") imageActionsRef.current.onRestoreImage?.(name);
        else imageActionsRef.current.onDeleteImage?.(name);
        return;
      }
      if (target.closest(".vditor-wysiwyg__preview")) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    host.addEventListener("click", keepRenderedBlocksVisible, true);

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
          if (!readOnly) onChangeRef.current(stripEditorArtifacts(markdown));
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
          decorateImages();
          observer = new MutationObserver(decorateImages);
          observer.observe(host, { childList: true, subtree: true, attributes: true, attributeFilter: ["src"] });
        }
      });
    }

    void mountEditor();
    return () => {
      cancelled = true;
      host.removeEventListener("click", keepRenderedBlocksVisible, true);
      observer?.disconnect();
      editor?.destroy();
      editorRef.current = null;
    };
  }, [articleId, i18n.resolvedLanguage, readOnly, resolvedTheme, t]);

  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (editor.getValue() !== value) editor.setValue(value);
  }, [value]);

  return <div className={`markdown-editor${readOnly ? " markdown-editor-readonly" : ""}`} ref={hostRef} aria-label={t("article.editorLabel")} />;
}
