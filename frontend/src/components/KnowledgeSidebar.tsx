import {
  ArrowCounterClockwise,
  CaretDown,
  CaretRight,
  Check,
  DotsThree,
  FilePlus,
  FileText,
  MagnifyingGlass,
  Note,
  NotePencil,
  PencilSimple,
  Plus,
  Trash,
  WarningCircle,
  X
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type DragEvent, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { matchPath, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import type { ArticleSummary, CollectionNode } from "../types";

function articleIdFromPath(pathname: string) {
  const encoded = matchPath("/articles/:articleId", pathname)?.params.articleId ?? "";
  if (!encoded) return "";
  try {
    return decodeURIComponent(encoded);
  } catch {
    return encoded;
  }
}

function ArticleLeaf({
  article,
  active,
  editing,
  dragging,
  onSelect,
  onDelete,
  onDragStart,
  onDragEnd
}: {
  article: ArticleSummary;
  active: boolean;
  editing: boolean;
  dragging: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onDragStart: (event: DragEvent<HTMLButtonElement>) => void;
  onDragEnd: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div
      className={`knowledge-article-row${active ? " active" : ""}${editing ? " editing" : ""}${dragging ? " dragging" : ""}`}
      title={t("knowledge.dragArticle", { title: article.title })}
    >
      <button
        type="button"
        className="knowledge-article-leaf"
        aria-current={active ? "page" : undefined}
        draggable
        onClick={onSelect}
        onDragStart={onDragStart}
        onDragEnd={onDragEnd}
      >
        <FileText size={14} weight={active ? "fill" : "regular"} />
        <span>{article.title}</span>
      </button>
      {editing && (
        <button
          type="button"
          className="knowledge-article-delete"
          aria-label={t("knowledge.deleteArticle", { title: article.title })}
          title={t("knowledge.deleteArticle", { title: article.title })}
          onClick={onDelete}
        >
          <Trash size={13} />
        </button>
      )}
    </div>
  );
}

function containsCollection(node: CollectionNode, collectionId: string): boolean {
  return node.id === collectionId || node.children.some((child) => containsCollection(child, collectionId));
}

function deletedCollectionRoots(nodes: CollectionNode[]): CollectionNode[] {
  const deleted: CollectionNode[] = [];
  for (const node of nodes) {
    if (node.retired) {
      deleted.push(node);
      continue;
    }
    deleted.push(...deletedCollectionRoots(node.children));
  }
  return deleted;
}

function CollectionBranch({
  collection,
  articles,
  selectedArticleId,
  selectedCollectionId,
  activeCollectionId,
  editingArticles,
  draggingArticleId,
  renamingId,
  renameValue,
  pendingDeleteId,
  busy,
  onSelectArticle,
  onDeleteArticle,
  onMoveArticle,
  onDragArticleStart,
  onDragArticleEnd,
  onSelectCollection,
  onCreateChild,
  onBeginRename,
  onRenameValue,
  onSaveRename,
  onCancelRename,
  onDelete
}: {
  collection: CollectionNode;
  articles: ArticleSummary[];
  selectedArticleId: string;
  selectedCollectionId: string;
  activeCollectionId: string;
  editingArticles: boolean;
  draggingArticleId: string | null;
  renamingId: string | null;
  renameValue: string;
  pendingDeleteId: string | null;
  busy: boolean;
  onSelectArticle: (articleId: string) => void;
  onDeleteArticle: (article: ArticleSummary) => void;
  onMoveArticle: (articleId: string, collectionId: string) => void;
  onDragArticleStart: (articleId: string, event: DragEvent<HTMLButtonElement>) => void;
  onDragArticleEnd: () => void;
  onSelectCollection: (collectionId: string) => void;
  onCreateChild: (collection: CollectionNode) => void;
  onBeginRename: (collection: CollectionNode) => void;
  onRenameValue: (value: string) => void;
  onSaveRename: (collection: CollectionNode) => void;
  onCancelRename: () => void;
  onDelete: (collection: CollectionNode) => void;
}) {
  const { t } = useTranslation();
  const directArticles = articles.filter(
    (article) => article.collection?.collection_id === collection.id
  );
  const selectedInside = Boolean(
    selectedCollectionId && containsCollection(collection, selectedCollectionId)
  );
  const selected = activeCollectionId === collection.id;
  const [open, setOpen] = useState(selectedInside || directArticles.length > 0);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => {
    if (selectedInside) setOpen(true);
  }, [selectedInside]);

  return (
    <div className="collection-branch">
      <div
        className={`collection-row${selected ? " current-path" : ""}${selectedInside && !selected ? " contains-selection" : ""}${dragOver && draggingArticleId ? " drop-target" : ""}`}
        title={draggingArticleId ? t("knowledge.dropArticleInside", { name: collection.name }) : undefined}
        onDragOver={(event) => {
          if (!draggingArticleId) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          setDragOver(true);
        }}
        onDragLeave={(event) => {
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          setDragOver(false);
        }}
        onDrop={(event) => {
          if (!draggingArticleId) return;
          event.preventDefault();
          event.stopPropagation();
          setDragOver(false);
          setOpen(true);
          const articleId = event.dataTransfer.getData("application/x-noosphere-article-id")
            || draggingArticleId;
          onMoveArticle(articleId, collection.id);
        }}
      >
        <button
          type="button"
          className="collection-toggle"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <CaretDown size={12} /> : <CaretRight size={12} />}
          <Note size={16} weight={selectedInside ? "fill" : "duotone"} />
        </button>
        {renamingId === collection.id ? (
          <form
            className="collection-rename-form"
            onSubmit={(event) => {
              event.preventDefault();
              onSaveRename(collection);
            }}
          >
            <input
              value={renameValue}
              maxLength={80}
              autoFocus
              onChange={(event) => onRenameValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") onCancelRename();
              }}
            />
            <button type="submit" disabled={busy || !renameValue.trim()} aria-label={t("common.save")}>
              <Check size={13} />
            </button>
            <button type="button" onClick={onCancelRename} aria-label={t("common.cancel")}>
              <X size={13} />
            </button>
          </form>
        ) : (
          <>
            <button type="button" className="collection-name" onClick={() => onSelectCollection(collection.id)}>
              <span>{collection.name}</span>
              <small>{collection.article_count}</small>
            </button>
            <div className="collection-row-actions">
              <button
                type="button"
                aria-label={t("knowledge.addInside", { name: collection.name })}
                title={t("knowledge.addInside", { name: collection.name })}
                onClick={() => {
                  setOpen(true);
                  onCreateChild(collection);
                }}
              >
                <FilePlus size={14} />
              </button>
              <button
                type="button"
                aria-label={t("knowledge.renameCollection", { name: collection.name })}
                title={t("knowledge.renameCollection", { name: collection.name })}
                onClick={() => onBeginRename(collection)}
              >
                <PencilSimple size={13} />
              </button>
              {editingArticles && (
                <button
                  type="button"
                  className={pendingDeleteId === collection.id ? "confirming" : ""}
                  aria-label={pendingDeleteId === collection.id
                    ? t("knowledge.confirmDeleteCollection", { name: collection.name })
                    : t("knowledge.deleteCollection", { name: collection.name })}
                  title={pendingDeleteId === collection.id
                    ? t("knowledge.clickAgainToConfirm")
                    : t("knowledge.deleteCollection", { name: collection.name })}
                  onClick={() => onDelete(collection)}
                >
                  {pendingDeleteId === collection.id ? <Check size={13} /> : <Trash size={13} />}
                </button>
              )}
            </div>
          </>
        )}
      </div>
      {open && (
        <div className="collection-children">
          {directArticles.map((article) => (
            <ArticleLeaf
              article={article}
              active={selectedArticleId === article.id}
              editing={editingArticles}
              dragging={draggingArticleId === article.id}
              onSelect={() => onSelectArticle(article.id)}
              onDelete={() => onDeleteArticle(article)}
              onDragStart={(event) => onDragArticleStart(article.id, event)}
              onDragEnd={onDragArticleEnd}
              key={article.id}
            />
          ))}
          {collection.children.map((child) => (
            <CollectionBranch
              collection={child}
              articles={articles}
              selectedArticleId={selectedArticleId}
              selectedCollectionId={selectedCollectionId}
              activeCollectionId={activeCollectionId}
              editingArticles={editingArticles}
              draggingArticleId={draggingArticleId}
              renamingId={renamingId}
              renameValue={renameValue}
              pendingDeleteId={pendingDeleteId}
              busy={busy}
              onSelectArticle={onSelectArticle}
              onDeleteArticle={onDeleteArticle}
              onMoveArticle={onMoveArticle}
              onDragArticleStart={onDragArticleStart}
              onDragArticleEnd={onDragArticleEnd}
              onSelectCollection={onSelectCollection}
              onCreateChild={onCreateChild}
              onBeginRename={onBeginRename}
              onRenameValue={onRenameValue}
              onSaveRename={onSaveRename}
              onCancelRename={onCancelRename}
              onDelete={onDelete}
              key={child.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function KnowledgeSidebar({ onCapture }: { onCapture: () => void }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = useState("");
  const [headerMenuOpen, setHeaderMenuOpen] = useState(false);
  const [deletedCollectionsOpen, setDeletedCollectionsOpen] = useState(false);
  const [editingArticles, setEditingArticles] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createParent, setCreateParent] = useState<CollectionNode | null>(null);
  const [createName, setCreateName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [articleToDelete, setArticleToDelete] = useState<ArticleSummary | null>(null);
  const [draggingArticleId, setDraggingArticleId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState("");
  const selectedArticleId = articleIdFromPath(location.pathname);
  const articleQuery = useQuery({
    queryKey: ["articles", i18n.resolvedLanguage],
    queryFn: api.listArticles
  });
  const collectionQuery = useQuery({
    queryKey: ["collections", i18n.resolvedLanguage],
    queryFn: api.getCollections
  });
  const managedCollectionQuery = useQuery({
    queryKey: ["collections", "managed", i18n.resolvedLanguage],
    queryFn: api.getManagedCollections,
    enabled: deletedCollectionsOpen
  });
  const articles = articleQuery.data?.articles ?? [];
  const collections = collectionQuery.data?.collections ?? [];
  const selectedArticle = articles.find((article) => article.id === selectedArticleId);
  const activeCollectionId = matchPath("/collections/:collectionId", location.pathname)?.params.collectionId ?? "";
  const selectedCollectionId = activeCollectionId
    || selectedArticle?.collection?.collection_id
    || "";
  const visibleArticles = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase();
    if (!normalized) return articles;
    return articles.filter((article) =>
      [article.title, article.platformLabel, article.author, ...(article.searchTerms ?? [])]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(normalized))
    );
  }, [articles, search]);
  const rootArticles = visibleArticles.filter((article) => !article.collection?.collection_id);
  const deletedCollections = deletedCollectionRoots(managedCollectionQuery.data?.collections ?? []);

  async function refresh() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["collections"] }),
      queryClient.invalidateQueries({ queryKey: ["articles"] }),
      queryClient.invalidateQueries({ queryKey: ["article"] })
    ]);
  }

  const createMutation = useMutation({
    mutationFn: api.createCollection,
    onSuccess: async () => {
      setCreateName("");
      setCreateOpen(false);
      setCreateParent(null);
      setFeedback("");
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message)
  });
  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: string; values: { name?: string; retired?: boolean } }) =>
      api.updateCollection(id, values),
    onSuccess: async () => {
      setRenamingId(null);
      setPendingDeleteId(null);
      setFeedback("");
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message)
  });
  const restoreCollectionMutation = useMutation({
    mutationFn: (collectionId: string) => api.updateCollection(collectionId, { retired: false }),
    onSuccess: async () => {
      setFeedback("");
      await Promise.all([
        refresh(),
        queryClient.invalidateQueries({ queryKey: ["collections", "managed"] })
      ]);
    },
    onError: (error: Error) => setFeedback(error.message)
  });
  const trashMutation = useMutation({
    mutationFn: (articleId: string) => api.trashArticles([articleId]),
    onSuccess: async (_, articleId) => {
      const deletingSelectedArticle = articleId === selectedArticleId;
      setArticleToDelete(null);
      setFeedback("");
      await Promise.all([
        refresh(),
        queryClient.invalidateQueries({ queryKey: ["article-trash"] })
      ]);
      if (deletingSelectedArticle) {
        navigate(selectedCollectionId ? `/collections/${encodeURIComponent(selectedCollectionId)}` : "/");
      }
    },
    onError: (error: Error) => setFeedback(error.message)
  });
  const moveMutation = useMutation({
    mutationFn: ({ articleId, collectionId }: { articleId: string; collectionId: string }) =>
      api.updateArticleCollection(articleId, collectionId),
    onSuccess: async () => {
      setFeedback("");
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message),
    onSettled: () => setDraggingArticleId(null)
  });
  const busy = createMutation.isPending || updateMutation.isPending || restoreCollectionMutation.isPending || trashMutation.isPending || moveMutation.isPending;

  useEffect(() => {
    if (!headerMenuOpen) return;
    const closeMenu = (event: PointerEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof PointerEvent && (event.target as Element | null)?.closest(".knowledge-header-menu")) return;
      setHeaderMenuOpen(false);
    };
    document.addEventListener("pointerdown", closeMenu);
    document.addEventListener("keydown", closeMenu);
    return () => {
      document.removeEventListener("pointerdown", closeMenu);
      document.removeEventListener("keydown", closeMenu);
    };
  }, [headerMenuOpen]);

  function beginCreate(parent: CollectionNode | null) {
    setCreateParent(parent);
    setCreateName("");
    setCreateOpen(true);
    setFeedback("");
  }

  function selectArticle(articleId: string) {
    navigate(`/articles/${encodeURIComponent(articleId)}`);
  }

  function selectCollection(collectionId: string) {
    navigate(`/collections/${encodeURIComponent(collectionId)}`);
  }

  function beginArticleDrag(articleId: string, event: DragEvent<HTMLButtonElement>) {
    setDraggingArticleId(articleId);
    setFeedback("");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("application/x-noosphere-article-id", articleId);
    event.dataTransfer.setData("text/plain", articleId);
  }

  function moveArticle(articleId: string, collectionId: string) {
    const article = articles.find((item) => item.id === articleId);
    if (article?.collection?.collection_id === collectionId) {
      setDraggingArticleId(null);
      return;
    }
    moveMutation.mutate({ articleId, collectionId });
  }

  return (
    <section className="library-sidebar-workspace">
      <header className="library-sidebar-header">
        <h2>{t("knowledge.title")}</h2>
        <div className="library-header-actions">
          <div className="knowledge-header-menu">
            <button
              type="button"
              className={headerMenuOpen || editingArticles ? "active" : ""}
              aria-expanded={headerMenuOpen}
              aria-haspopup="menu"
              aria-label={t("knowledge.moreActions")}
              title={t("knowledge.moreActions")}
              onClick={() => setHeaderMenuOpen((open) => !open)}
            >
              <DotsThree size={19} weight="bold" />
            </button>
            {headerMenuOpen && (
              <div className="knowledge-header-menu-popover" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setHeaderMenuOpen(false);
                    beginCreate(null);
                  }}
                >
                  <FilePlus size={16} />
                  <span><strong>{t("knowledge.newCategory")}</strong><small>{t("knowledge.newCategoryHelp")}</small></span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className={editingArticles ? "active" : ""}
                  onClick={() => {
                    setHeaderMenuOpen(false);
                    setEditingArticles((editing) => !editing);
                    setArticleToDelete(null);
                    setPendingDeleteId(null);
                  }}
                >
                  <PencilSimple size={16} />
                  <span>
                    <strong>{editingArticles ? t("knowledge.finishEditingArticles") : t("knowledge.editArticles")}</strong>
                    <small>{t("knowledge.editArticlesHelp")}</small>
                  </span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setHeaderMenuOpen(false);
                    setDeletedCollectionsOpen(true);
                    setFeedback("");
                  }}
                >
                  <ArrowCounterClockwise size={16} />
                  <span>
                    <strong>{t("knowledge.deletedCollections")}</strong>
                    <small>{t("knowledge.deletedCollectionsHelp")}</small>
                  </span>
                </button>
              </div>
            )}
          </div>
          <button type="button" onClick={onCapture} aria-label={t("capture.button")} title={t("capture.button")}>
            <Plus size={16} weight="bold" />
          </button>
        </div>
      </header>
      <label className="knowledge-search">
        <MagnifyingGlass size={15} />
        <input
          type="search"
          value={search}
          placeholder={t("knowledge.search")}
          aria-label={t("knowledge.search")}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      {createOpen && (
        <form
          className="collection-create-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!createName.trim()) return;
            createMutation.mutate({
              name: createName.trim(),
              parentId: createParent?.id
            });
          }}
        >
          <span>{createParent ? t("knowledge.createInside", { name: createParent.name }) : t("knowledge.createAtRoot")}</span>
          <div>
            <input
              value={createName}
              maxLength={80}
              autoFocus
              placeholder={t("knowledge.collectionName")}
              onChange={(event) => setCreateName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setCreateOpen(false);
              }}
            />
            <button type="submit" disabled={busy || !createName.trim()} aria-label={t("common.confirm")}>
              <Check size={14} />
            </button>
            <button type="button" onClick={() => setCreateOpen(false)} aria-label={t("common.cancel")}>
              <X size={14} />
            </button>
          </div>
        </form>
      )}
      {feedback && <p className="library-sidebar-error" role="alert">{feedback}</p>}
      <div className="library-sidebar-tree">
        {(articleQuery.isLoading || collectionQuery.isLoading) && (
          <div className="library-sidebar-loading" aria-label={t("knowledge.loading")}>
            <i />
            <i />
            <i />
          </div>
        )}
        {(articleQuery.isError || collectionQuery.isError) && (
          <p className="library-sidebar-error">{((articleQuery.error ?? collectionQuery.error) as Error).message}</p>
        )}
        {rootArticles.length > 0 && (
          <div className="collection-root-articles">
            {rootArticles.map((article) => (
              <ArticleLeaf
                article={article}
                active={selectedArticleId === article.id}
                editing={editingArticles}
                dragging={draggingArticleId === article.id}
                onSelect={() => selectArticle(article.id)}
                onDelete={() => setArticleToDelete(article)}
                onDragStart={(event) => beginArticleDrag(article.id, event)}
                onDragEnd={() => setDraggingArticleId(null)}
                key={article.id}
              />
            ))}
          </div>
        )}
        {collections.map((collection) => (
          <CollectionBranch
            collection={collection}
            articles={visibleArticles}
            selectedArticleId={selectedArticleId}
            selectedCollectionId={selectedCollectionId}
            activeCollectionId={activeCollectionId}
            editingArticles={editingArticles}
            draggingArticleId={draggingArticleId}
            renamingId={renamingId}
            renameValue={renameValue}
            pendingDeleteId={pendingDeleteId}
            busy={busy}
            onSelectArticle={selectArticle}
            onDeleteArticle={setArticleToDelete}
            onMoveArticle={moveArticle}
            onDragArticleStart={beginArticleDrag}
            onDragArticleEnd={() => setDraggingArticleId(null)}
            onSelectCollection={selectCollection}
            onCreateChild={beginCreate}
            onBeginRename={(item) => {
              setRenamingId(item.id);
              setRenameValue(item.name);
              setPendingDeleteId(null);
            }}
            onRenameValue={setRenameValue}
            onSaveRename={(item) => {
              if (renameValue.trim() && renameValue.trim() !== item.name) {
                updateMutation.mutate({ id: item.id, values: { name: renameValue.trim() } });
              } else {
                setRenamingId(null);
              }
            }}
            onCancelRename={() => setRenamingId(null)}
            onDelete={(item) => {
              if (pendingDeleteId === item.id) {
                updateMutation.mutate({ id: item.id, values: { retired: true } });
              } else {
                setPendingDeleteId(item.id);
                setRenamingId(null);
              }
            }}
            key={collection.id}
          />
        ))}
        {!articleQuery.isLoading && visibleArticles.length === 0 && collections.length === 0 && (
          <div className="knowledge-tree-empty">
            <NotePencil size={25} weight="duotone" />
            <p>{search ? t("knowledge.noSearchResults") : t("knowledge.emptyCollections")}</p>
          </div>
        )}
      </div>
      {articleToDelete && createPortal(
        <div className="dialog-layer modal-root-layer" role="presentation" onMouseDown={() => !trashMutation.isPending && setArticleToDelete(null)}>
          <section
            className="article-confirm-dialog knowledge-delete-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="knowledge-delete-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <span className="article-confirm-icon article-confirm-icon-removed"><WarningCircle size={24} /></span>
            <div>
              <h2 id="knowledge-delete-title">{t("knowledge.deleteArticleTitle")}</h2>
              <p>{t("knowledge.deleteArticleDescription", { title: articleToDelete.title })}</p>
              <div className="dialog-actions">
                <button className="button-secondary" type="button" disabled={trashMutation.isPending} onClick={() => setArticleToDelete(null)}>
                  {t("common.cancel")}
                </button>
                <button className="button-danger" type="button" disabled={trashMutation.isPending} onClick={() => trashMutation.mutate(articleToDelete.id)}>
                  <Trash size={15} />
                  {t("knowledge.moveArticleToTrash")}
                </button>
              </div>
            </div>
          </section>
        </div>,
        document.body
      )}
      {deletedCollectionsOpen && createPortal(
        <div className="dialog-layer modal-root-layer" role="presentation" onMouseDown={() => !restoreCollectionMutation.isPending && setDeletedCollectionsOpen(false)}>
          <section
            className="collection-restore-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="collection-restore-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header>
              <div>
                <h2 id="collection-restore-title">{t("knowledge.deletedCollections")}</h2>
                <p>{t("knowledge.deletedCollectionsDescription")}</p>
              </div>
              <button type="button" disabled={restoreCollectionMutation.isPending} onClick={() => setDeletedCollectionsOpen(false)} aria-label={t("nav.close")}>
                <X size={17} />
              </button>
            </header>
            {managedCollectionQuery.isLoading && (
              <div className="collection-restore-loading" aria-label={t("knowledge.loading")}><i /><i /></div>
            )}
            {managedCollectionQuery.isError && (
              <p className="library-sidebar-error" role="alert">{(managedCollectionQuery.error as Error).message}</p>
            )}
            {!managedCollectionQuery.isLoading && !managedCollectionQuery.isError && deletedCollections.length === 0 && (
              <div className="collection-restore-empty">
                <Check size={20} />
                <p>{t("knowledge.noDeletedCollections")}</p>
              </div>
            )}
            {deletedCollections.length > 0 && (
              <div className="collection-restore-list">
                {deletedCollections.map((collection) => (
                  <article key={collection.id}>
                    <Note size={18} weight="duotone" />
                    <span>
                      <strong>{collection.name}</strong>
                      <small>{t("knowledge.deletedCollectionCount", { count: collection.article_count })}</small>
                    </span>
                    <button
                      className="button-secondary compact-button"
                      type="button"
                      disabled={restoreCollectionMutation.isPending}
                      onClick={() => restoreCollectionMutation.mutate(collection.id)}
                    >
                      <ArrowCounterClockwise
                        className={restoreCollectionMutation.isPending && restoreCollectionMutation.variables === collection.id ? "spin" : ""}
                        size={14}
                      />
                      {t("knowledge.restoreCollection")}
                    </button>
                  </article>
                ))}
              </div>
            )}
            {restoreCollectionMutation.isError && <p className="library-sidebar-error" role="alert">{(restoreCollectionMutation.error as Error).message}</p>}
          </section>
        </div>,
        document.body
      )}
    </section>
  );
}
