import { useEffect, useState, type CSSProperties } from "react";
import { useTranslation } from "react-i18next";

export interface SettingsSectionNavItem {
  id: string;
  labelKey: string;
  lineClass: "line-short" | "line-medium" | "line-long";
}

const defaultSections: SettingsSectionNavItem[] = [
  { id: "settings-review", labelKey: "reviewStudio.reviewSection", lineClass: "line-long" },
  { id: "settings-ai", labelKey: "settings.aiTitle", lineClass: "line-medium" },
  { id: "settings-crawlers", labelKey: "settings.crawlersTitle", lineClass: "line-long" },
  { id: "settings-destinations", labelKey: "settings.destinationsTitle", lineClass: "line-medium" }
] as const;

export function SettingsSectionNav({
  sections = defaultSections,
  ariaLabel
}: {
  sections?: SettingsSectionNavItem[];
  ariaLabel?: string;
}) {
  const { t } = useTranslation();
  const [activeId, setActiveId] = useState(sections[0]?.id ?? "");
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const itemHeight = Math.max(10, Math.min(18, 84 / sections.length));
  const navStyle = {
    "--settings-nav-item-height": `${itemHeight}px`,
    "--settings-nav-half-height": `${(itemHeight * sections.length) / 2}px`
  } as CSSProperties;

  useEffect(() => {
    const elements = sections.map(({ id }) => document.getElementById(id)).filter((element): element is HTMLElement => Boolean(element));
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]?.target.id) setActiveId(visible[0].target.id);
    }, { rootMargin: "-16% 0px -66% 0px", threshold: [0, 0.05] });
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  function goTo(id: string) {
    setActiveId(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <nav
      className="settings-section-nav"
      aria-label={ariaLabel ?? t("settings.sectionNavLabel")}
      onPointerLeave={() => setHoveredIndex(null)}
      style={navStyle}
    >
      <div className="settings-section-nav-inner">
        {sections.map((section, index) => {
          const waveDistance = hoveredIndex === null ? "idle" : String(Math.min(Math.abs(index - hoveredIndex), 3));
          return (
            <button
              type="button"
              key={section.id}
              className={activeId === section.id ? "active" : ""}
              data-wave-distance={waveDistance}
              aria-current={activeId === section.id ? "location" : undefined}
              aria-label={t(section.labelKey)}
              onPointerEnter={() => setHoveredIndex(index)}
              onFocus={() => setHoveredIndex(index)}
              onBlur={() => setHoveredIndex(null)}
              onClick={() => goTo(section.id)}
            >
              <span className={`settings-nav-line ${section.lineClass}`} aria-hidden="true" />
              <span className="settings-nav-tooltip" aria-hidden="true">
                <span className="settings-nav-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="settings-nav-label">{t(section.labelKey)}</span>
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
