import {
  BookOpenText,
  CaretDown,
  CaretRight,
  FileText,
  FolderOpen,
  FolderSimple,
  MagnifyingGlass,
  NoteBlank,
  TreeStructure
} from "@phosphor-icons/react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, matchPath, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { ArticleSummary, TaxonomyTag } from "../types";

function ArticleLeaf({
  article,
  active,
  onSelect
}: {
  article: ArticleSummary;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`knowledge-article-leaf${active ? " active" : ""}`}
      aria-current={active ? "page" : undefined}
      onClick={onSelect}
    >
      <FileText size={15} weight={active ? "fill" : "regular"} />
      <span>{article.title}</span>
    </button>
  );
}

function CategoryBranch({
  category,
  articles,
  selectedId,
  onSelect
}: {
  category: TaxonomyTag;
  articles: ArticleSummary[];
  selectedId: string;
  onSelect: (articleId: string) => void;
}) {
  const directArticles = articles.filter(
    (article) => article.classification?.tag_id === category.id && !article.classification.subtag_id
  );
  const childArticles = (childId: string) =>
    articles.filter((article) => article.classification?.subtag_id === childId);
  const count = directArticles.length + category.children.reduce((total, child) => total + childArticles(child.id).length, 0);
  const [open, setOpen] = useState(count > 0);

  return (
    <div className="knowledge-category-branch">
      <button
        type="button"
        className="knowledge-tree-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? <CaretDown size={13} /> : <CaretRight size={13} />}
        {open ? <FolderOpen size={17} weight="duotone" /> : <FolderSimple size={17} weight="duotone" />}
        <span>{category.name}</span>
        <small>{count}</small>
      </button>
      {open && (
        <div className="knowledge-tree-children">
          {directArticles.map((article) => (
            <ArticleLeaf
              article={article}
              active={selectedId === article.id}
              onSelect={() => onSelect(article.id)}
              key={article.id}
            />
          ))}
          {category.children.map((child) => {
            const assigned = childArticles(child.id);
            return (
              <div className="knowledge-subcategory" key={child.id}>
                <div className="knowledge-subcategory-label" title={child.description}>
                  <TreeStructure size={13} />
                  <span>{child.name}</span>
                  <small>{assigned.length}</small>
                </div>
                {assigned.map((article) => (
                  <ArticleLeaf
                    article={article}
                    active={selectedId === article.id}
                    onSelect={() => onSelect(article.id)}
                    key={article.id}
                  />
                ))}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function articleIdFromPath(pathname: string) {
  const encoded = matchPath("/articles/:articleId", pathname)?.params.articleId ?? "";
  if (!encoded) return "";
  try {
    return decodeURIComponent(encoded);
  } catch {
    return encoded;
  }
}

export function KnowledgeSidebar({ active }: { active: boolean }) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = useState("");
  const selectedId = articleIdFromPath(location.pathname);
  const articleQuery = useQuery({
    queryKey: ["articles", i18n.resolvedLanguage],
    queryFn: api.listArticles,
    enabled: active
  });
  const taxonomyQuery = useQuery({
    queryKey: ["taxonomy", i18n.resolvedLanguage],
    queryFn: api.getTaxonomy,
    enabled: active
  });
  const articles = articleQuery.data?.articles ?? [];
  const taxonomy = taxonomyQuery.data?.tags ?? [];
  const visibleArticles = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase();
    if (!normalized) return articles;
    return articles.filter((article) =>
      [article.title, article.platformLabel, article.author, ...(article.searchTerms ?? [])]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(normalized))
    );
  }, [articles, search]);
  const activeCategoryIds = useMemo(
    () => new Set(taxonomy.flatMap((root) => [root.id, ...root.children.map((child) => child.id)])),
    [taxonomy]
  );
  const unclassified = visibleArticles.filter((article) => {
    const classification = article.classification;
    if (!classification) return true;
    return !activeCategoryIds.has(classification.subtag_id ?? classification.tag_id);
  });

  function selectArticle(articleId: string) {
    navigate(`/articles/${encodeURIComponent(articleId)}`);
  }

  return (
    <section className="library-sidebar-workspace" aria-hidden={!active}>
      <header className="library-sidebar-header">
        <div>
          <p className="context-label">{t("knowledge.eyebrow")}</p>
          <h1>{t("knowledge.title")}</h1>
        </div>
        <span>{articles.length}</span>
      </header>
      <label className="knowledge-search">
        <MagnifyingGlass size={16} />
        <input
          type="search"
          value={search}
          placeholder={t("knowledge.search")}
          aria-label={t("knowledge.search")}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      <div className="library-sidebar-tree">
        {(articleQuery.isLoading || taxonomyQuery.isLoading) && (
          <div className="library-sidebar-loading" aria-label={t("knowledge.loading")}>
            <i />
            <i />
            <i />
          </div>
        )}
        {(articleQuery.isError || taxonomyQuery.isError) && (
          <p className="library-sidebar-error">{((articleQuery.error ?? taxonomyQuery.error) as Error).message}</p>
        )}
        {taxonomy.map((root) => (
          <CategoryBranch
            category={root}
            articles={visibleArticles}
            selectedId={selectedId}
            onSelect={selectArticle}
            key={root.id}
          />
        ))}
        {unclassified.length > 0 && (
          <div className="knowledge-unclassified">
            <div className="knowledge-subcategory-label">
              <NoteBlank size={14} />
              <span>{t("knowledge.unclassified")}</span>
              <small>{unclassified.length}</small>
            </div>
            {unclassified.map((article) => (
              <ArticleLeaf
                article={article}
                active={selectedId === article.id}
                onSelect={() => selectArticle(article.id)}
                key={article.id}
              />
            ))}
          </div>
        )}
        {!articleQuery.isLoading && visibleArticles.length === 0 && (
          <div className="knowledge-tree-empty">
            <BookOpenText size={25} weight="duotone" />
            <p>{search ? t("knowledge.noSearchResults") : t("knowledge.noArticles")}</p>
          </div>
        )}
      </div>
      <Link className="library-manage-link" to="/review-studio">
        <TreeStructure size={15} />
        {t("knowledge.manageCategories")}
      </Link>
    </section>
  );
}
