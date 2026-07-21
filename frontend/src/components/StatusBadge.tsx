import type { ArticleStatus } from "../types";
import { useTranslation } from "react-i18next";

export function StatusBadge({ status }: { status: ArticleStatus }) {
  const { t } = useTranslation();
  return <span className={`status-badge status-${status}`}>{t(`status.${status}`)}</span>;
}
