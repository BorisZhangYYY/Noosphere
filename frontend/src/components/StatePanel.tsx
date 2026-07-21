import { WarningCircle } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";

export function LoadingPanel({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className="state-panel" aria-live="polite">
      <div className="skeleton skeleton-title" />
      <div className="skeleton skeleton-line" />
      <div className="skeleton skeleton-line skeleton-short" />
      <span className="sr-only">{label ?? t("common.loadingLibrary")}</span>
    </div>
  );
}

export function ErrorPanel({ message }: { message: string }) {
  const { t } = useTranslation();
  return (
    <div className="state-panel error-panel" role="alert">
      <WarningCircle size={24} />
      <div><strong>{t("common.attentionTitle")}</strong><p>{message}</p></div>
    </div>
  );
}
