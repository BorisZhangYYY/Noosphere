import {
  BookOpenText,
  Gear,
  Moon,
  Path,
  Plus,
  SidebarSimple,
  Sun,
  Translate,
  UploadSimple,
  X
} from "@phosphor-icons/react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Atmosphere } from "./Atmosphere";
import { useTheme } from "../theme";
import { InlineSelect } from "./InlineSelect";
import type { ReviewMode } from "../types";

const navItems = [
  { to: "/library", labelKey: "nav.library", icon: BookOpenText },
  { to: "/pipeline", labelKey: "nav.pipeline", icon: Path },
  { to: "/sources", labelKey: "nav.sources", icon: UploadSimple },
  { to: "/settings", labelKey: "nav.settings", icon: Gear }
];

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [captureUrl, setCaptureUrl] = useState("");
  const pipelineSettings = useQuery({ queryKey: ["pipeline-settings"], queryFn: api.getPipelineSettings });
  const [reviewMode, setReviewMode] = useState<ReviewMode>("ai_then_manual");
  const [perspective, setPerspective] = useState("original");
  const { resolvedTheme, toggleTheme } = useTheme();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const captureMutation = useMutation({
    mutationFn: api.createCapture,
    onSuccess: () => {
      setCaptureOpen(false);
      setCaptureUrl("");
      navigate("/pipeline");
    }
  });

  useEffect(() => {
    if (!pipelineSettings.data) return;
    setReviewMode(pipelineSettings.data.reviewMode);
    setPerspective(pipelineSettings.data.activePerspective);
  }, [pipelineSettings.data]);

  return (
    <div className="app-root">
      <Atmosphere />
      <button className="mobile-menu" aria-label={t("nav.open")} onClick={() => setMobileOpen(true)}>
        <SidebarSimple size={21} />
      </button>
      <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <NavLink to="/" className="brand" onClick={() => setMobileOpen(false)}>
            <img className="brand-mark" src="/app/noosphere-mark.svg" alt="" />
            <span>Noosphere</span>
          </NavLink>
          <button className="sidebar-close" onClick={() => setMobileOpen(false)} aria-label={t("nav.close")}>
            <X size={19} />
          </button>
        </div>

        <nav className="primary-nav" aria-label={t("nav.primary")}>
          {navItems.map(({ to, labelKey, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `nav-item ${isActive ? "nav-item-active" : ""}`}
            >
              <Icon size={20} weight="regular" />
              <span>{t(labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button className="theme-button" onClick={toggleTheme} aria-label={t("controls.toggleTheme")}>
            {resolvedTheme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
            <span>{resolvedTheme === "dark" ? t("controls.lightMode") : t("controls.darkMode")}</span>
          </button>
          <button className="language-button" onClick={() => void i18n.changeLanguage(i18n.resolvedLanguage === "zh" ? "en" : "zh")} aria-label={t("controls.switchLanguage")}>
            <Translate size={19} />
            <span>{t("controls.language")}</span>
          </button>
          <button className="capture-button" onClick={() => setCaptureOpen(true)}>
            <Plus size={18} weight="bold" />
            <span>{t("capture.button")}</span>
          </button>
        </div>
      </aside>

      {mobileOpen && <button className="sidebar-scrim" aria-label={t("nav.close")} onClick={() => setMobileOpen(false)} />}
      <main className="content-shell"><Outlet /></main>

      {captureOpen && (
        <div className="dialog-layer" role="presentation" onMouseDown={() => setCaptureOpen(false)}>
          <form className="capture-dialog" role="dialog" aria-modal="true" aria-labelledby="capture-title" onSubmit={(event) => { event.preventDefault(); captureMutation.mutate({ url: captureUrl, reviewMode, perspective }); }} onMouseDown={(event) => event.stopPropagation()}>
            <button className="dialog-close" onClick={() => setCaptureOpen(false)} aria-label={t("nav.close")}>
              <X size={19} />
            </button>
            <p className="context-label">{t("capture.eyebrow")}</p>
            <h2 id="capture-title">{t("capture.title")}</h2>
            <p>{t("capture.description")}</p>
            <label className="field-label" htmlFor="capture-url">{t("capture.urlLabel")}</label>
            <input id="capture-url" type="url" placeholder="https://mp.weixin.qq.com/s/..." value={captureUrl} onChange={(event) => setCaptureUrl(event.target.value)} required autoFocus />
            <label className="settings-field"><span>{t("capture.reviewMode")}</span><InlineSelect value={reviewMode} onChange={setReviewMode} ariaLabel={t("capture.reviewMode")} options={[
              { value: "ai_then_manual", label: t("pipeline.modes.aiThenManual"), description: t("pipeline.modes.aiThenManualHelp") },
              { value: "manual_only", label: t("pipeline.modes.manualOnly"), description: t("pipeline.modes.manualOnlyHelp") }
            ]} /></label>
            {reviewMode === "ai_then_manual" && <label className="settings-field"><span>{t("capture.perspective")}</span><InlineSelect value={perspective} onChange={setPerspective} ariaLabel={t("capture.perspective")} options={(pipelineSettings.data?.perspectives ?? []).map((item) => ({ value: item.id, label: item.label, description: item.description }))} /></label>}
            <div className="dialog-actions">
              <button className="button-secondary" type="button" onClick={() => setCaptureOpen(false)}>{t("common.cancel")}</button>
              <button className="button-primary" type="submit" disabled={captureMutation.isPending}>{captureMutation.isPending ? t("capture.submitting") : t("capture.submit")}</button>
            </div>
            {captureMutation.isError && <p className="helper-text dialog-error" role="alert">{(captureMutation.error as Error).message}</p>}
            {!captureMutation.isError && <p className="helper-text">{t("capture.helper")}</p>}
          </form>
        </div>
      )}
    </div>
  );
}
