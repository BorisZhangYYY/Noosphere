import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

const sections = [
  { id: "settings-ai", labelKey: "settings.aiTitle", lineClass: "line-medium" },
  { id: "settings-review", labelKey: "pipeline.controlTitle", lineClass: "line-short" },
  { id: "settings-crawlers", labelKey: "settings.crawlersTitle", lineClass: "line-long" },
  { id: "settings-destinations", labelKey: "settings.destinationsTitle", lineClass: "line-medium" }
] as const;

export function SettingsSectionNav() {
  const { t } = useTranslation();
  const [activeId, setActiveId] = useState(sections[0].id);
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  useEffect(() => {
    const elements = sections.map(({ id }) => document.getElementById(id)).filter((element): element is HTMLElement => Boolean(element));
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]?.target.id) setActiveId(visible[0].target.id as typeof activeId);
    }, { rootMargin: "-16% 0px -66% 0px", threshold: [0, 0.05] });
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  function goTo(id: string) {
    setActiveId(id as typeof activeId);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <nav className="settings-section-nav" aria-label={t("settings.sectionNavLabel")} onPointerLeave={() => setHoveredIndex(null)}>
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
