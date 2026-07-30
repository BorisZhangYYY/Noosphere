import { MagicWand, BracketsCurly, FileText } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";
import { PipelineSettingsPanel } from "../components/PipelineSettingsPanel";
import { SettingsSectionNav, type SettingsSectionNavItem } from "../components/SettingsSectionNav";

const reviewSections: SettingsSectionNavItem[] = [
  { id: "settings-review", labelKey: "reviewStudio.reviewSection", lineClass: "line-long" }
];

export function ReviewStudioPage() {
  const { t } = useTranslation();
  return (
    <div className="page review-studio-page">
      <header className="page-header review-studio-header">
        <div>
          <p className="context-label">{t("reviewStudio.eyebrow")}</p>
          <h1>{t("reviewStudio.title")}</h1>
          <p>{t("reviewStudio.description")}</p>
        </div>
        <div className="review-contract-badge">
          <span><MagicWand size={18} />{t("reviewStudio.aiRole")}</span>
          <i>+</i>
          <span><BracketsCurly size={18} />{t("reviewStudio.systemRole")}</span>
          <i>→</i>
          <strong><FileText size={18} />{t("reviewStudio.result")}</strong>
        </div>
      </header>
      <div className="review-studio-content-layout">
        <SettingsSectionNav sections={reviewSections} ariaLabel={t("reviewStudio.sectionNavLabel")} />
        <div className="review-studio-stack">
          <PipelineSettingsPanel />
        </div>
      </div>
    </div>
  );
}
