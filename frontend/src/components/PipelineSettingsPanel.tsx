import { FloppyDisk, Plus, SpinnerGap, Trash } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import type { OutputLanguage, PipelinePerspective, PipelineSettings, ReviewMode } from "../types";
import { InlineSelect } from "./InlineSelect";

export function PipelineSettingsPanel() {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [promptTab, setPromptTab] = useState<"perspective" | "template">("perspective");
  const [draft, setDraft] = useState<PipelineSettings | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const query = useQuery({ queryKey: ["pipeline-settings", i18n.resolvedLanguage], queryFn: api.getPipelineSettings });
  useEffect(() => { if (query.data) setDraft(query.data); }, [query.data]);
  const mutation = useMutation({
    mutationFn: api.updatePipelineSettings,
    onSuccess: async (data) => {
      setDraft(data);
      setPendingDelete(null);
      await queryClient.invalidateQueries({ queryKey: ["pipeline-settings"] });
    }
  });

  if (!draft) return null;
  const active = draft.perspectives.find((item) => item.id === draft.activePerspective) ?? draft.perspectives[0];
  const promptEditable = Boolean(active?.editable);
  const editorValue = promptTab === "perspective" ? active?.prompt ?? "" : active?.template ?? "";

  function updateActive(changes: Partial<PipelinePerspective>) {
    setDraft((current) => current ? {
      ...current,
      perspectives: current.perspectives.map((item) => item.id === current.activePerspective ? { ...item, ...changes } : item)
    } : current);
  }

  function createPerspective() {
    if (!active) return;
    const id = `custom_${Date.now().toString(36)}`;
    const perspective: PipelinePerspective = {
      ...active,
      id,
      label: t("pipeline.customPerspectiveName"),
      description: t("pipeline.customPerspectiveDescription"),
      prompt: active.prompt,
      template: active.template,
      builtin: false,
      editable: true,
      outputSections: { ...active.outputSections }
    };
    setDraft((current) => current ? { ...current, activePerspective: id, perspectives: [...current.perspectives, perspective] } : current);
    setPromptTab("perspective");
    setPendingDelete(null);
  }

  function deletePerspective() {
    if (!active?.editable) return;
    if (pendingDelete !== active.id) {
      setPendingDelete(active.id);
      return;
    }
    setDraft((current) => {
      if (!current) return current;
      const perspectives = current.perspectives.filter((item) => item.id !== active.id);
      return { ...current, activePerspective: perspectives[0].id, perspectives };
    });
    setPendingDelete(null);
  }

  const templateFields = ["title", "source_metadata", ...Object.keys(active?.outputSections ?? {})];

  return <section className="settings-group pipeline-control-panel" id="settings-review">
    <div className="group-heading group-heading-action">
      <div><h2>{t("pipeline.controlTitle")}</h2><p>{t("pipeline.controlDescription")}</p></div>
      <button className="button-primary" type="button" onClick={() => mutation.mutate(draft)} disabled={mutation.isPending}>
        {mutation.isPending ? <SpinnerGap className="spin" size={17} /> : <FloppyDisk size={17} />}{t("pipeline.saveSettings")}
      </button>
    </div>

    <div className="pipeline-control-grid pipeline-control-grid-compact">
      <label className="settings-field"><span>{t("pipeline.reviewMode")}</span><InlineSelect<ReviewMode> value={draft.reviewMode} onChange={(reviewMode) => setDraft({ ...draft, reviewMode })} ariaLabel={t("pipeline.reviewMode")} options={[{ value: "ai_then_manual", label: t("pipeline.modes.aiThenManual"), description: t("pipeline.modes.aiThenManualHelp") }, { value: "auto_upload", label: t("pipeline.modes.autoUpload"), description: t("pipeline.modes.autoUploadHelp") }]} /></label>
      <label className="settings-field"><span>{t("pipeline.outputLanguage")}</span><InlineSelect<OutputLanguage> value={draft.outputLanguage} onChange={(outputLanguage) => setDraft({ ...draft, outputLanguage })} ariaLabel={t("pipeline.outputLanguage")} options={(['follow_ui', 'source', 'zh-CN', 'en-US'] as const).map((value) => ({ value, label: t(`pipeline.languages.${value}`), description: t(`pipeline.languagesHelp.${value}`) }))} /></label>
    </div>

    <div className="prompt-formula" aria-label={t("pipeline.promptFormulaLabel")}><span>{t("pipeline.promptTabs.common")}</span><i>+</i><span>{t("pipeline.promptTabs.perspective")}</span><i>+</i><span>{t("pipeline.promptTabs.template")}</span><b>→</b><strong>{t("pipeline.promptContract")}</strong></div>

    <section className="prompt-layer common-prompt-layer">
      <div className="prompt-layer-heading">
        <div><span className="prompt-layer-index">1</span><div><h3>{t("pipeline.commonLayerTitle")}</h3><p>{t("pipeline.promptHelp.common")}</p></div></div>
        <span className="readonly-badge">{t("pipeline.readonly")}</span>
      </div>
      <textarea className="prompt-editor common-prompt-editor" value={draft.commonPrompt} readOnly aria-label={t("pipeline.promptTabs.common")} spellCheck={false} />
    </section>

    <section className="prompt-layer perspective-prompt-layer">
      <div className="prompt-layer-heading perspective-layer-heading">
        <div><span className="prompt-layer-index">2</span><div><h3>{t("pipeline.perspectiveLayerTitle")}</h3><p>{t("pipeline.perspectiveLayerDescription")}</p></div></div>
        <div className="perspective-actions">
          <button className="button-secondary compact-button" type="button" onClick={createPerspective}><Plus size={16} />{t("pipeline.addPerspective")}</button>
          {active?.editable && <button className={pendingDelete === active.id ? "button-danger compact-button" : "button-secondary compact-button"} type="button" onClick={deletePerspective}><Trash size={16} />{pendingDelete === active.id ? t("common.confirm") : t("pipeline.deletePerspective")}</button>}
        </div>
      </div>

      <div className="perspective-selector-row">
        <label className="settings-field"><span>{t("pipeline.perspective")}</span><InlineSelect value={draft.activePerspective} onChange={(activePerspective) => { setDraft({ ...draft, activePerspective }); setPendingDelete(null); }} ariaLabel={t("pipeline.perspective")} options={draft.perspectives.map((item) => ({ value: item.id, label: item.label, description: item.description }))} /></label>
        {active?.editable ? <div className="perspective-meta-fields">
          <label><span>{t("pipeline.perspectiveName")}</span><input value={active.label} maxLength={80} onChange={(event) => updateActive({ label: event.target.value })} /></label>
          <label><span>{t("pipeline.perspectiveDescription")}</span><input value={active.description} maxLength={400} onChange={(event) => updateActive({ description: event.target.value })} /></label>
        </div> : <div className="builtin-perspective-note"><span className="readonly-badge">{t("pipeline.builtin")}</span><p>{t("pipeline.builtinPerspectiveHelp")}</p></div>}
      </div>

      <div className="prompt-tabs" role="tablist" aria-label={t("pipeline.promptTabsLabel")}>
        {(["perspective", "template"] as const).map((tab) => <button key={tab} type="button" role="tab" aria-selected={promptTab === tab} className={promptTab === tab ? "active" : ""} onClick={() => setPromptTab(tab)}>{t(`pipeline.promptTabs.${tab}`)}</button>)}
      </div>
      <p className="prompt-help">{t(`pipeline.promptHelp.${promptTab}`)} {!promptEditable && t("pipeline.builtinReadonly")}</p>

      <div className={`perspective-editor-layout${promptTab === "template" ? " template-editor-layout" : ""}`}>
        <textarea className="prompt-editor" value={editorValue} onChange={(event) => updateActive(promptTab === "perspective" ? { prompt: event.target.value } : { template: event.target.value })} spellCheck={false} disabled={!promptEditable} />
        {promptTab === "template" && <aside className="template-guide" aria-label={t("pipeline.templateGuideTitle")}>
          <h4>{t("pipeline.templateGuideTitle")}</h4>
          <p>{t("pipeline.templateGuideDescription")}</p>
          <div className="template-field-list">{templateFields.map((field) => <code key={field}>{`{{${field}}}`}</code>)}</div>
          <ol>
            <li>{t("pipeline.templateGuideExact")}</li>
            <li>{t("pipeline.templateGuideHeadings")}</li>
            <li>{t("pipeline.templateGuideMetadata")}</li>
          </ol>
        </aside>}
      </div>
    </section>

    {mutation.isSuccess && <p className="validation-ok" role="status">{t("pipeline.settingsSaved")}</p>}
    {mutation.isError && <p className="article-action-error" role="alert">{(mutation.error as Error).message}</p>}
  </section>;
}
