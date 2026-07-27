import {
  ArrowSquareOut,
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
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import { Link, useSearchParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { api } from "../api";
import { articleOutlineFromMarkdown } from "../components/ArticleOutline";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import type { ArticleSummary, TaxonomyTag } from "../types";

function headingId(label: string) {
  return `knowledge-heading-${label
    .normalize("NFKC")
    .toLocaleLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-|-$/g, "")}`;
}

function nodeText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (node && typeof node === "object" && "props" in node) {
    return nodeText((node as { props?: { children?: ReactNode } }).props?.children);
  }
  return "";
}

function withoutLeadingTitle(markdown: string) {
  return markdown.replace(/^\s*#\s+.+?(?:\r?\n)+/, "");
}

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

export function KnowledgePage() {
  const { t, i18n } = useTranslation();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const articleQuery = useQuery({
    queryKey: ["articles", i18n.resolvedLanguage],
    queryFn: api.listArticles
  });
  const taxonomyQuery = useQuery({
    queryKey: ["taxonomy", i18n.resolvedLanguage],
    queryFn: api.getTaxonomy
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
  const selectedId = params.get("article") ?? "";
  const selectedSummary = articles.find((article) => article.id === selectedId);
  const detailQuery = useQuery({
    queryKey: ["article", selectedId, i18n.resolvedLanguage],
    queryFn: () => api.getArticle(selectedId),
    enabled: Boolean(selectedId)
  });
  const activeCategoryIds = useMemo(
    () => new Set(taxonomy.flatMap((root) => [root.id, ...root.children.map((child) => child.id)])),
    [taxonomy]
  );
  const unclassified = visibleArticles.filter((article) => {
    const classification = article.classification;
    if (!classification) return true;
    return !activeCategoryIds.has(classification.subtag_id ?? classification.tag_id);
  });
  const readerMarkdown = withoutLeadingTitle(detailQuery.data?.displayMarkdown ?? "");
  const outline = articleOutlineFromMarkdown(readerMarkdown);

  useEffect(() => {
    if (selectedSummary || articles.length === 0) return;
    setParams({ article: articles[0].id }, { replace: true });
  }, [articles, selectedSummary, setParams]);

  function selectArticle(articleId: string) {
    setParams({ article: articleId });
  }

  const markdownComponents = useMemo(() => {
    const heading = (Tag: "h1" | "h2" | "h3" | "h4" | "h5" | "h6") =>
      ({ children, ...props }: { children?: ReactNode }) => {
        const label = nodeText(children);
        return <Tag id={headingId(label)} {...props}>{children}</Tag>;
      };
    return {
      h1: heading("h1"),
      h2: heading("h2"),
      h3: heading("h3"),
      h4: heading("h4"),
      h5: heading("h5"),
      h6: heading("h6"),
      img: ({ src, alt }: { src?: string; alt?: string }) => {
        if (!src || !selectedId) return null;
        let resolved = src;
        if (src.startsWith("assets/")) {
          resolved = `/api/v1/articles/${encodeURIComponent(selectedId)}/assets/${encodeURIComponent(src.slice(7))}`;
        } else if (src.startsWith("removed/")) {
          resolved = `/api/v1/articles/${encodeURIComponent(selectedId)}/removed/${encodeURIComponent(src.slice(8))}`;
        }
        return <img src={resolved} alt={alt ?? ""} loading="lazy" />;
      }
    };
  }, [selectedId]);

  if (articleQuery.isLoading || taxonomyQuery.isLoading) {
    return <div className="page knowledge-page"><LoadingPanel label={t("knowledge.loading")} /></div>;
  }
  if (articleQuery.isError || taxonomyQuery.isError) {
    const error = articleQuery.error ?? taxonomyQuery.error;
    return <div className="page knowledge-page"><ErrorPanel message={(error as Error).message} /></div>;
  }

  return (
    <div className="page knowledge-page">
      <section className="knowledge-workspace">
        <aside className="knowledge-tree-pane">
          <header className="knowledge-pane-header">
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
          <div className="knowledge-tree-scroll">
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
            {visibleArticles.length === 0 && (
              <div className="knowledge-tree-empty">
                <BookOpenText size={25} weight="duotone" />
                <p>{search ? t("knowledge.noSearchResults") : t("knowledge.noArticles")}</p>
              </div>
            )}
          </div>
          <footer className="knowledge-tree-footer">
            <Link to="/review-studio">{t("knowledge.manageCategories")}</Link>
            <Link to="/">{t("knowledge.openOverview")}</Link>
          </footer>
        </aside>

        <nav className="knowledge-outline-pane" aria-label={t("knowledge.outline")}>
          <header>
            <span>{t("knowledge.outline")}</span>
            <small>{outline.length}</small>
          </header>
          <div className="knowledge-outline-list">
            {outline.map((item, index) => (
              <button
                type="button"
                className={`knowledge-outline-level-${Math.min(item.level, 4)}`}
                onClick={() => document.getElementById(headingId(item.label))?.scrollIntoView({ behavior: "smooth", block: "start" })}
                key={`${item.label}-${index}`}
              >
                <i>{String(index + 1).padStart(2, "0")}</i>
                <span>{item.label}</span>
              </button>
            ))}
            {selectedId && outline.length === 0 && <p>{t("knowledge.noOutline")}</p>}
          </div>
        </nav>

        <main className="knowledge-reader-pane">
          {!selectedId && (
            <div className="knowledge-reader-empty">
              <BookOpenText size={36} weight="duotone" />
              <h2>{t("knowledge.selectTitle")}</h2>
              <p>{t("knowledge.selectDescription")}</p>
            </div>
          )}
          {selectedId && detailQuery.isLoading && <LoadingPanel label={t("common.loadingArticle")} />}
          {selectedId && detailQuery.isError && <ErrorPanel message={(detailQuery.error as Error).message} />}
          {detailQuery.data && (
            <>
              <header className="knowledge-reader-header">
                <div>
                  <div className="knowledge-breadcrumb">
                    <span>{detailQuery.data.classification?.tag_name ?? t("knowledge.unclassified")}</span>
                    {detailQuery.data.classification?.subtag_name && (
                      <>
                        <CaretRight size={12} />
                        <span>{detailQuery.data.classification.subtag_name}</span>
                      </>
                    )}
                  </div>
                  <h2>{detailQuery.data.title}</h2>
                  <p>
                    {detailQuery.data.platformLabel}
                    {detailQuery.data.author ? ` · ${detailQuery.data.author}` : ""}
                  </p>
                </div>
                <Link to={`/articles/${encodeURIComponent(detailQuery.data.id)}`} className="button-secondary">
                  {t("knowledge.openWorkbench")}
                  <ArrowSquareOut size={16} />
                </Link>
              </header>
              <article className="knowledge-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                  {readerMarkdown}
                </ReactMarkdown>
              </article>
            </>
          )}
        </main>
      </section>
    </div>
  );
}
