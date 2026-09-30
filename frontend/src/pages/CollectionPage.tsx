import {
  ArrowRight,
  CaretRight,
  Check,
  FileText,
  Note,
  PencilSimple,
  Sparkle,
  X
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import type { CollectionNode } from "../types";

function findCollection(
  collections: CollectionNode[],
  collectionId: string,
  path: CollectionNode[] = []
): { collection: CollectionNode; path: CollectionNode[] } | null {
  for (const collection of collections) {
    const nextPath = [...path, collection];
    if (collection.id === collectionId) return { collection, path: nextPath };
    const nested = findCollection(collection.children, collectionId, nextPath);
    if (nested) return nested;
  }
  return null;
}

export function CollectionPage() {
  const { collectionId = "" } = useParams();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editingCollectionId, setEditingCollectionId] = useState<string | null>(null);
  const [description, setDescription] = useState("");
  const activeCollectionIdRef = useRef(collectionId);
  const editingCollectionIdRef = useRef<string | null>(null);
  const editRevisionRef = useRef(0);
  activeCollectionIdRef.current = collectionId;
  const editingDescription = editingCollectionId === collectionId;
  const collectionQuery = useQuery({ queryKey: ["collections", i18n.resolvedLanguage], queryFn: api.getCollections });
  const articleQuery = useQuery({
    queryKey: ["articles", i18n.resolvedLanguage],
    queryFn: api.listArticles
  });
  const match = useMemo(
    () => findCollection(collectionQuery.data?.collections ?? [], collectionId),
    [collectionId, collectionQuery.data]
  );
  const directArticles = (articleQuery.data?.articles ?? []).filter(
    (article) => article.collection?.collection_id === collectionId
  );
  const updateMutation = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string; revision: number }) =>
      api.updateCollection(id, { description: value }),
    onSuccess: async (_result, variables) => {
      if (
        activeCollectionIdRef.current === variables.id &&
        editingCollectionIdRef.current === variables.id &&
        editRevisionRef.current === variables.revision
      ) {
        editRevisionRef.current += 1;
        editingCollectionIdRef.current = null;
        setEditingCollectionId(null);
      }
      await queryClient.invalidateQueries({ queryKey: ["collections"] });
    }
  });
  const polishMutation = useMutation({
    mutationFn: ({ name, value }: { name: string; value: string; id: string; revision: number }) =>
      api.polishCollectionDescription({ name, description: value }),
    onSuccess: (result, variables) => {
      if (
        activeCollectionIdRef.current !== variables.id ||
        editingCollectionIdRef.current !== variables.id ||
        editRevisionRef.current !== variables.revision
      ) return;
      editRevisionRef.current += 1;
      setDescription(result.description);
    }
  });

  useEffect(() => {
    editRevisionRef.current += 1;
    editingCollectionIdRef.current = null;
    setEditingCollectionId(null);
    setDescription("");
  }, [collectionId]);

  if (collectionQuery.isLoading || articleQuery.isLoading) {
    return <div className="page"><LoadingPanel label={t("knowledge.loading")} /></div>;
  }
  if (collectionQuery.isError || articleQuery.isError) {
    return <div className="page"><ErrorPanel message={((collectionQuery.error ?? articleQuery.error) as Error).message} /></div>;
  }
  if (!match) {
    return <div className="page"><ErrorPanel message={t("knowledge.collectionNotFound")} /></div>;
  }

  const { collection, path } = match;
  const introduction = collection.description || t("knowledge.defaultCollectionIntroduction", { name: collection.name });

  return (
    <div className="page collection-page">
      <nav className="collection-document-breadcrumb" aria-label={t("article.breadcrumb")}>
        <button type="button" onClick={() => navigate("/")}>{t("knowledge.title")}</button>
        {path.map((item, index) => (
          <span key={item.id}>
            <CaretRight size={12} />
            {index === path.length - 1
              ? <strong>{item.name}</strong>
              : <Link to={`/collections/${encodeURIComponent(item.id)}`}>{item.name}</Link>}
          </span>
        ))}
      </nav>

      <article className="collection-index-document">
        <header>
          <div className="collection-index-kicker"><Note size={17} weight="duotone" />{t("knowledge.indexDocument")}</div>
          <h1>{collection.name}</h1>
          {editingDescription ? (
            <form
              className="collection-description-editor"
              onSubmit={(event) => {
                event.preventDefault();
                updateMutation.mutate({
                  id: collection.id,
                  value: description.trim(),
                  revision: editRevisionRef.current
                });
              }}
            >
              <textarea
                value={description}
                autoFocus
                maxLength={600}
                onChange={(event) => {
                  editRevisionRef.current += 1;
                  setDescription(event.target.value);
                }}
              />
              <div>
                <button
                  className="button-secondary compact-button"
                  type="button"
                  disabled={!description.trim() || polishMutation.isPending}
                  onClick={() => polishMutation.mutate({
                    id: collection.id,
                    name: collection.name,
                    value: description,
                    revision: editRevisionRef.current
                  })}
                >
                  <Sparkle size={15} />{t("knowledge.polishIntroduction")}
                </button>
                <button className="button-primary compact-button" type="submit" disabled={updateMutation.isPending}>
                  <Check size={15} />{t("common.save")}
                </button>
                <button className="button-secondary compact-button" type="button" onClick={() => {
                  editRevisionRef.current += 1;
                  editingCollectionIdRef.current = null;
                  setEditingCollectionId(null);
                  polishMutation.reset();
                }}>
                  <X size={15} />{t("common.cancel")}
                </button>
              </div>
              {polishMutation.isError ? (
                <small className="collection-polish-error">{t("knowledge.polishIntroductionFailed")}</small>
              ) : null}
            </form>
          ) : (
            <blockquote>
              <p>{introduction}</p>
              <button
                type="button"
                onClick={() => {
                  editRevisionRef.current += 1;
                  editingCollectionIdRef.current = collection.id;
                  setDescription(collection.description);
                  setEditingCollectionId(collection.id);
                  polishMutation.reset();
                }}
                aria-label={t("knowledge.editIntroduction")}
              >
                <PencilSimple size={14} />{t("knowledge.editIntroduction")}
              </button>
            </blockquote>
          )}
        </header>

        <section className="collection-index-contents">
          <div className="collection-index-heading">
            <div><span>02</span><h2>{t("knowledge.contents")}</h2></div>
            <small>{t("knowledge.contentsCount", { count: collection.children.length + directArticles.length })}</small>
          </div>
          {collection.children.length === 0 && directArticles.length === 0 ? (
            <p className="collection-index-empty">{t("knowledge.emptyIndexDocument")}</p>
          ) : (
            <div className="collection-index-list">
              {collection.children.map((child) => (
                <Link className="collection-index-row collection-index-row-child" to={`/collections/${encodeURIComponent(child.id)}`} key={child.id}>
                  <span className="collection-index-row-icon"><Note size={20} weight="duotone" /></span>
                  <span><strong>{child.name}</strong><small>{child.description || t("knowledge.nestedIndexDocument")}</small></span>
                  <em>{child.article_count}</em>
                  <ArrowRight size={17} />
                </Link>
              ))}
              {directArticles.map((article) => (
                <Link className="collection-index-row" to={`/articles/${encodeURIComponent(article.id)}`} key={article.id}>
                  <span className="collection-index-row-icon"><FileText size={19} /></span>
                  <span><strong>{article.title}</strong><small>{article.author || article.platformLabel}</small></span>
                  <ArrowRight size={17} />
                </Link>
              ))}
            </div>
          )}
        </section>
      </article>
    </div>
  );
}
