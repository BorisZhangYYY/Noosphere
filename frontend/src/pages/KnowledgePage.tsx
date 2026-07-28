import { BookOpenText } from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate } from "react-router-dom";
import { api } from "../api";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";

export function KnowledgePage() {
  const { t, i18n } = useTranslation();
  const articleQuery = useQuery({
    queryKey: ["articles", i18n.resolvedLanguage],
    queryFn: api.listArticles
  });

  if (articleQuery.isLoading) {
    return <div className="page library-entry-page"><LoadingPanel label={t("knowledge.loading")} /></div>;
  }
  if (articleQuery.isError) {
    return <div className="page library-entry-page"><ErrorPanel message={(articleQuery.error as Error).message} /></div>;
  }

  const firstArticle = articleQuery.data?.articles[0];
  if (firstArticle) {
    return <Navigate to={`/articles/${encodeURIComponent(firstArticle.id)}`} replace />;
  }

  return (
    <div className="page library-entry-page">
      <section className="library-entry-empty">
        <BookOpenText size={42} weight="duotone" />
        <h1>{t("knowledge.title")}</h1>
        <p>{t("knowledge.noArticles")}</p>
      </section>
    </div>
  );
}
