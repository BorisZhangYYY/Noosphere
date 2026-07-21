import { FloppyDisk, SpinnerGap } from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import type { PipelineSettings, ReviewMode } from "../types";
import { InlineSelect } from "./InlineSelect";

export function PipelineSettingsPanel() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [promptTab, setPromptTab] = useState<"common" | "perspective" | "template">("common");
  const [draft, setDraft] = useState<PipelineSettings | null>(null);
  const query = useQuery({ queryKey: ["pipeline-settings"], queryFn: api.getPipelineSettings });
  useEffect(() => { if (query.data) setDraft(query.data); }, [query.data]);
  const mutation = useMutation({ mutationFn: api.updatePipelineSettings, onSuccess: async (data) => { setDraft(data); await queryClient.invalidateQueries({ queryKey: ["pipeline-settings"] }); } });
  if (!draft) return null;
  const manualOnly = draft.reviewMode === "manual_only";
  const active = draft.perspectives.find((item) => item.id === draft.activePerspective);
  const value = promptTab === "common" ? draft.commonPrompt : promptTab === "perspective" ? active?.prompt ?? "" : active?.template ?? "";
  const updatePrompt = (next: string) => setDraft((current) => {
    if (!current) return current;
    if (promptTab === "common") return { ...current, commonPrompt: next };
    return { ...current, perspectives: current.perspectives.map((item) => item.id === current.activePerspective ? { ...item, [promptTab === "perspective" ? "prompt" : "template"]: next } : item) };
  });
  return <section className="settings-group pipeline-control-panel" id="settings-review">
    <div className="group-heading group-heading-action"><div><h2>{t("pipeline.controlTitle")}</h2><p>{t("pipeline.controlDescription")}</p></div><button className="button-primary" type="button" onClick={() => mutation.mutate(draft)} disabled={mutation.isPending}>{mutation.isPending ? <SpinnerGap className="spin" size={17} /> : <FloppyDisk size={17} />}{t("pipeline.saveSettings")}</button></div>
    <div className="pipeline-control-grid">
      <label className="settings-field"><span>{t("pipeline.reviewMode")}</span><InlineSelect<ReviewMode> value={draft.reviewMode} onChange={(reviewMode) => setDraft({ ...draft, reviewMode })} ariaLabel={t("pipeline.reviewMode")} options={[{ value: "ai_then_manual", label: t("pipeline.modes.aiThenManual"), description: t("pipeline.modes.aiThenManualHelp") }, { value: "manual_only", label: t("pipeline.modes.manualOnly"), description: t("pipeline.modes.manualOnlyHelp") }]} /></label>
      <label className={`settings-field${manualOnly ? " settings-field-disabled" : ""}`}><span>{t("pipeline.perspective")}</span><InlineSelect value={draft.activePerspective} onChange={(activePerspective) => setDraft({ ...draft, activePerspective })} ariaLabel={t("pipeline.perspective")} disabled={manualOnly} options={draft.perspectives.map((item) => ({ value: item.id, label: item.label, description: item.description }))} /></label>
    </div>
    <div className={`prompt-workspace${manualOnly ? " prompt-workspace-disabled" : ""}`} aria-disabled={manualOnly}>
      <div className="prompt-formula" aria-label={t("pipeline.promptFormulaLabel")}><span>{t("pipeline.promptTabs.common")}</span><i>+</i><span>{t("pipeline.promptTabs.perspective")}</span><i>+</i><span>{t("pipeline.promptTabs.template")}</span><b>→</b><strong>{t("pipeline.promptContract")}</strong></div>
      <div className="prompt-tabs" role="tablist" aria-label={t("pipeline.promptTabsLabel")}>{(["common", "perspective", "template"] as const).map((tab) => <button key={tab} type="button" role="tab" disabled={manualOnly} aria-selected={promptTab === tab} className={promptTab === tab ? "active" : ""} onClick={() => setPromptTab(tab)}>{t(`pipeline.promptTabs.${tab}`)}</button>)}</div>
      <p className="prompt-help">{manualOnly ? t("pipeline.modes.manualOnlyHelp") : t(`pipeline.promptHelp.${promptTab}`)}</p>
      <textarea className="prompt-editor" value={value} onChange={(event) => updatePrompt(event.target.value)} spellCheck={false} disabled={manualOnly} />
    </div>
    {mutation.isSuccess && <p className="validation-ok" role="status">{t("pipeline.settingsSaved")}</p>}
    {mutation.isError && <p className="article-action-error" role="alert">{(mutation.error as Error).message}</p>}
  </section>;
}
