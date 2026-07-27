import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";

interface OutlineHeading {
  level: number;
  label: string;
}

function plainHeading(value: string) {
  return value
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*_~]/g, "")
    .trim();
}

export function articleOutlineFromMarkdown(markdown: string): OutlineHeading[] {
  const headings: OutlineHeading[] = [];
  let fence = "";
  for (const line of markdown.split(/\r?\n/)) {
    const fenceMatch = line.match(/^\s*(`{3,}|~{3,})/);
    if (fenceMatch) {
      const marker = fenceMatch[1][0];
      fence = fence === marker ? "" : marker;
      continue;
    }
    if (fence) continue;
    const match = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (!match) continue;
    const label = plainHeading(match[2]);
    if (label) headings.push({ level: match[1].length, label });
  }
  return headings;
}

export function ArticleOutline({ markdown }: { markdown: string }) {
  const { t } = useTranslation();
  const headings = useMemo(() => articleOutlineFromMarkdown(markdown), [markdown]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const itemHeight = Math.max(10, Math.min(18, 216 / headings.length));

  useEffect(() => {
    const host = document.querySelector<HTMLElement>(".markdown-editor");
    const scrollRoot = document.querySelector<HTMLElement>(".article-page .reader-surface");
    if (!host || !scrollRoot || headings.length === 0) return;
    let headingObserver: IntersectionObserver | null = null;
    const bindHeadings = () => {
      headingObserver?.disconnect();
      const nodes = host.querySelectorAll<HTMLElement>(".vditor-wysiwyg > .vditor-reset > :is(h1,h2,h3,h4,h5,h6)");
      headingObserver = new IntersectionObserver((entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        const index = Number((visible[0]?.target as HTMLElement | undefined)?.dataset.outlineIndex);
        if (Number.isFinite(index)) setActiveIndex(Math.min(index, headings.length - 1));
      }, { root: scrollRoot, rootMargin: "-24px 0px -68% 0px", threshold: [0, 0.05] });
      nodes.forEach((node, index) => {
        node.dataset.outlineIndex = String(index);
        headingObserver?.observe(node);
      });
    };
    const mutationObserver = new MutationObserver(bindHeadings);
    mutationObserver.observe(host, { childList: true, subtree: true });
    bindHeadings();
    return () => {
      headingObserver?.disconnect();
      mutationObserver.disconnect();
    };
  }, [headings.length]);

  if (headings.length === 0) return null;

  function goToHeading(index: number) {
    const nodes = document.querySelectorAll<HTMLElement>(".markdown-editor .vditor-wysiwyg > .vditor-reset > :is(h1,h2,h3,h4,h5,h6)");
    const target = nodes.item(index);
    const scrollRoot = document.querySelector<HTMLElement>(".article-page .reader-surface");
    if (!target || !scrollRoot) return;
    setActiveIndex(index);
    const targetTop = target.getBoundingClientRect().top - scrollRoot.getBoundingClientRect().top + scrollRoot.scrollTop;
    scrollRoot.scrollTo({ top: Math.max(0, targetTop - 24), behavior: "smooth" });
  }

  return (
    <nav
      className="article-outline"
      aria-label={t("article.outline")}
      onPointerLeave={() => setHoveredIndex(null)}
      style={{ "--article-outline-item-height": `${itemHeight}px` } as CSSProperties}
    >
      <span className="sr-only">{t("article.outline")}</span>
      <div className="article-outline-list">
        {headings.map((heading, index) => {
          const waveDistance = hoveredIndex === null ? "idle" : String(Math.min(Math.abs(index - hoveredIndex), 3));
          const baseWidth = Math.max(8, 19 - Math.min(heading.level - 1, 3) * 3);
          return (
            <button
              type="button"
              className={activeIndex === index ? "active" : ""}
              data-wave-distance={waveDistance}
              style={{ "--article-outline-base-width": `${baseWidth}px` } as CSSProperties}
              aria-current={activeIndex === index ? "location" : undefined}
              aria-label={heading.label}
              onPointerEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onBlur={() => setHoveredIndex(null)}
              onClick={() => goToHeading(index)}
              key={`${index}-${heading.label}`}
            >
              <span className="article-outline-line" aria-hidden="true" />
              <span className="article-outline-tooltip" aria-hidden="true">
                <span className="article-outline-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="article-outline-label">{heading.label}</span>
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
