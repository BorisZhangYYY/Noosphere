import {
  Archive,
  ArrowCounterClockwise,
  FloppyDisk,
  FolderSimple,
  FolderSimplePlus,
  Plus,
  SpinnerGap,
  TreeStructure
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import type { TaxonomyTag } from "../types";

function CategoryEditor({
  category,
  depth,
  onUpdate
}: {
  category: TaxonomyTag;
  depth: 1 | 2;
  onUpdate: (category: TaxonomyTag, values: { name: string; description: string }) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(category.name);
  const [description, setDescription] = useState(category.description);

  useEffect(() => {
    setName(category.name);
    setDescription(category.description);
  }, [category.description, category.name]);

  const changed = name.trim() !== category.name || description.trim() !== category.description;

  return (
    <div className={`taxonomy-editor-row taxonomy-editor-depth-${depth}${category.retired ? " retired" : ""}`}>
      <span className="taxonomy-level-mark" aria-hidden="true">
        {depth === 1 ? <FolderSimple size={18} weight="duotone" /> : <TreeStructure size={16} />}
      </span>
      <label>
        <span>{depth === 1 ? t("reviewStudio.taxonomy.typeName") : t("reviewStudio.taxonomy.subtypeName")}</span>
        <input
          value={name}
          maxLength={80}
          disabled={category.retired}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <label className="taxonomy-description-field">
        <span>{t("reviewStudio.taxonomy.shortDescription")}</span>
        <input
          value={description}
          maxLength={240}
          disabled={category.retired}
          placeholder={t("reviewStudio.taxonomy.descriptionPlaceholder")}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="button-secondary taxonomy-save-button"
        disabled={!changed || !name.trim() || category.retired}
        onClick={() => onUpdate(category, { name: name.trim(), description: description.trim() })}
      >
        <FloppyDisk size={15} />
        {t("common.save")}
      </button>
    </div>
  );
}

export function TaxonomyManager() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["taxonomy", "management", i18n.resolvedLanguage],
    queryFn: api.getManagedTaxonomy
  });
  const [parentId, setParentId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [feedback, setFeedback] = useState("");

  const roots = query.data?.tags ?? [];
  const activeRoots = useMemo(() => roots.filter((root) => !root.retired), [roots]);

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["taxonomy"] }),
      queryClient.invalidateQueries({ queryKey: ["articles"] })
    ]);
  };

  const createMutation = useMutation({
    mutationFn: api.createTaxonomyCategory,
    onSuccess: async () => {
      setName("");
      setDescription("");
      setFeedback(t("reviewStudio.taxonomy.created"));
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message)
  });

  const updateMutation = useMutation({
    mutationFn: ({ category, values }: { category: TaxonomyTag; values: { name?: string; description?: string; retired?: boolean } }) =>
      api.updateTaxonomyCategory(category.id, values),
    onSuccess: async (_, variables) => {
      setFeedback(
        variables.values.retired === true
          ? t("reviewStudio.taxonomy.retired")
          : variables.values.retired === false
            ? t("reviewStudio.taxonomy.restored")
            : t("reviewStudio.taxonomy.saved")
      );
      await refresh();
    },
    onError: (error: Error) => setFeedback(error.message)
  });

  const pending = createMutation.isPending || updateMutation.isPending;

  return (
    <section className="taxonomy-manager" aria-labelledby="taxonomy-manager-title">
      <div className="section-heading taxonomy-manager-heading">
        <div>
          <p className="context-label">{t("reviewStudio.taxonomy.eyebrow")}</p>
          <h2 id="taxonomy-manager-title">{t("reviewStudio.taxonomy.title")}</h2>
          <p>{t("reviewStudio.taxonomy.description")}</p>
        </div>
        <span className="taxonomy-depth-rule">
          <TreeStructure size={18} />
          {t("reviewStudio.taxonomy.depthRule")}
        </span>
      </div>

      <form
        className="taxonomy-create-row"
        onSubmit={(event) => {
          event.preventDefault();
          if (!name.trim()) return;
          setFeedback("");
          createMutation.mutate({
            name: name.trim(),
            description: description.trim(),
            parentId: parentId || undefined
          });
        }}
      >
        <label>
          <span>{t("reviewStudio.taxonomy.level")}</span>
          <select value={parentId} onChange={(event) => setParentId(event.target.value)}>
            <option value="">{t("reviewStudio.taxonomy.topLevel")}</option>
            {activeRoots.map((root) => (
              <option value={root.id} key={root.id}>
                {t("reviewStudio.taxonomy.under", { name: root.name })}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>{parentId ? t("reviewStudio.taxonomy.subtypeName") : t("reviewStudio.taxonomy.typeName")}</span>
          <input
            value={name}
            maxLength={80}
            placeholder={t("reviewStudio.taxonomy.namePlaceholder")}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className="taxonomy-description-field">
          <span>{t("reviewStudio.taxonomy.shortDescription")}</span>
          <input
            value={description}
            maxLength={240}
            placeholder={t("reviewStudio.taxonomy.descriptionPlaceholder")}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <button className="button-primary" type="submit" disabled={pending || !name.trim()}>
          {createMutation.isPending ? <SpinnerGap className="spin" size={16} /> : parentId ? <FolderSimplePlus size={16} /> : <Plus size={16} />}
          {t("reviewStudio.taxonomy.add")}
        </button>
      </form>

      {feedback && (
        <p className={createMutation.isError || updateMutation.isError ? "taxonomy-feedback error-message" : "taxonomy-feedback success-message"} role="status">
          {feedback}
        </p>
      )}

      {query.isLoading && <div className="taxonomy-loading">{t("common.loading")}</div>}
      {query.isError && <p className="taxonomy-feedback error-message">{(query.error as Error).message}</p>}
      {!query.isLoading && !query.isError && roots.length === 0 && (
        <div className="taxonomy-empty-state">
          <FolderSimplePlus size={30} weight="duotone" />
          <div>
            <h3>{t("reviewStudio.taxonomy.emptyTitle")}</h3>
            <p>{t("reviewStudio.taxonomy.emptyDescription")}</p>
          </div>
        </div>
      )}

      <div className="taxonomy-editor-tree">
        {roots.map((root) => (
          <article className={`taxonomy-family-editor${root.retired ? " retired" : ""}`} key={root.id}>
            <CategoryEditor
              category={root}
              depth={1}
              onUpdate={(category, values) => updateMutation.mutate({ category, values })}
            />
            <div className="taxonomy-family-actions">
              <button
                type="button"
                className="button-tertiary"
                disabled={pending}
                onClick={() => updateMutation.mutate({ category: root, values: { retired: !root.retired } })}
              >
                {root.retired ? <ArrowCounterClockwise size={15} /> : <Archive size={15} />}
                {root.retired ? t("reviewStudio.taxonomy.restore") : t("reviewStudio.taxonomy.retire")}
              </button>
            </div>
            {root.children.length > 0 && (
              <div className="taxonomy-child-editors">
                {root.children.map((child) => (
                  <div className="taxonomy-child-editor" key={child.id}>
                    <CategoryEditor
                      category={child}
                      depth={2}
                      onUpdate={(category, values) => updateMutation.mutate({ category, values })}
                    />
                    <button
                      type="button"
                      className="button-tertiary taxonomy-child-retire"
                      disabled={pending}
                      onClick={() => updateMutation.mutate({ category: child, values: { retired: !child.retired } })}
                    >
                      {child.retired ? <ArrowCounterClockwise size={15} /> : <Archive size={15} />}
                      {child.retired ? t("reviewStudio.taxonomy.restore") : t("reviewStudio.taxonomy.retire")}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}
