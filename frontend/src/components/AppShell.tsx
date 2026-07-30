import {
  Bird,
  ChatCircleText,
  Gear,
  Globe,
  House,
  Moon,
  Newspaper,
  Plus,
  Question,
  SidebarSimple,
  Sun,
  Translate,
  X
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { Atmosphere } from "./Atmosphere";
import { useTheme } from "../theme";
import { InlineSelect } from "./InlineSelect";
import { KnowledgeSidebar } from "./KnowledgeSidebar";
import type { CaptureJob, OutputLanguage, ReviewMode } from "../types";

const navItems = [
  { to: "/", labelKey: "nav.workspace", icon: House }
];

const helpSources = [
  { nameKey: "sources.wechat", host: "mp.weixin.qq.com", icon: ChatCircleText },
  { nameKey: "sources.zhihu", host: "zhuanlan.zhihu.com", icon: Newspaper },
  { nameKey: "sources.xiaoheihe", host: "xiaoheihe.cn", icon: Globe },
  { nameKey: "X", host: "x.com", icon: Bird }
];

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [captureUrl, setCaptureUrl] = useState("");
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const pipelineSettings = useQuery({ queryKey: ["pipeline-settings", i18n.resolvedLanguage], queryFn: api.getPipelineSettings });
  const [reviewMode, setReviewMode] = useState<ReviewMode>("ai_then_manual");
  const [perspective, setPerspective] = useState("original");
  const [outputLanguage, setOutputLanguage] = useState<OutputLanguage>("follow_ui");
  const { resolvedTheme, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const knowledgeMode = location.pathname === "/library"
    || location.pathname.startsWith("/articles/")
    || location.pathname.startsWith("/collections/");
  const captureMutation = useMutation({
    mutationFn: api.createCapture,
    onSuccess: async (job) => {
      queryClient.setQueryData<{ jobs: CaptureJob[] }>(["capture-jobs"], (current) => ({
        jobs: [job, ...(current?.jobs ?? []).filter((item) => item.id !== job.id)]
      }));
      setCaptureOpen(false);
      setCaptureUrl("");
      navigate("/");
      await queryClient.invalidateQueries({ queryKey: ["capture-jobs"] });
    }
  });

  useEffect(() => {
    if (!pipelineSettings.data) return;
    setReviewMode(pipelineSettings.data.reviewMode);
    setPerspective(pipelineSettings.data.activePerspective);
    setOutputLanguage(pipelineSettings.data.outputLanguage);
  }, [pipelineSettings.data]);

  return (
    <div className={`app-root${knowledgeMode ? " library-mode-active" : ""}`}>
      <Atmosphere />
      <button className="mobile-menu" aria-label={t("nav.open")} onClick={() => setMobileOpen(true)}>
        <SidebarSimple size={21} />
      </button>
      <aside className={`sidebar${mobileOpen ? " sidebar-open" : ""}`}>
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
              end
              onClick={() => setMobileOpen(false)}
              className={({ isActive }) => `nav-item nav-item-workspace ${isActive ? "nav-item-active" : ""}`}
            >
              <Icon size={20} weight="regular" />
              <span>{t(labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        <KnowledgeSidebar onCapture={() => setCaptureOpen(true)} />

        <div className="sidebar-footer">
          <NavLink className={({ isActive }) => `sidebar-utility-button${isActive ? " active" : ""}`} to="/settings" aria-label={t("nav.settings")} title={t("nav.settings")} onClick={() => setMobileOpen(false)}>
            <Gear size={18} />
          </NavLink>
          <button className={`sidebar-utility-button${helpOpen ? " active" : ""}`} onClick={() => setHelpOpen((open) => !open)} aria-label={t("help.title")} title={t("help.title")}>
            <Question size={18} />
          </button>
          <button className="theme-button" onClick={toggleTheme} aria-label={t("controls.toggleTheme")}>
            {resolvedTheme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
          </button>
          <button className="language-button" onClick={() => void i18n.changeLanguage(i18n.resolvedLanguage === "zh" ? "en" : "zh")} aria-label={t("controls.switchLanguage")}>
            <Translate size={19} />
            <span>{i18n.resolvedLanguage === "zh" ? "EN" : "中"}</span>
          </button>
        </div>
      </aside>

      {mobileOpen && <button className="sidebar-scrim" aria-label={t("nav.close")} onClick={() => setMobileOpen(false)} />}
      <main className="content-shell"><Outlet /></main>

      {helpOpen && (
        <div className="dialog-layer help-dialog-layer" role="presentation" onMouseDown={() => setHelpOpen(false)}>
          <section className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="help-dialog-title" onMouseDown={(event) => event.stopPropagation()}>
            <header>
              <div><p>{t("help.eyebrow")}</p><h2 id="help-dialog-title">{t("help.title")}</h2></div>
              <button type="button" onClick={() => setHelpOpen(false)} aria-label={t("nav.close")}><X size={18} /></button>
            </header>
            <p className="help-dialog-description">{t("help.description")}</p>
            <div className="help-steps">
              <div><span>01</span><p>{t("help.capture")}</p></div>
              <div><span>02</span><p>{t("help.organize")}</p></div>
              <div><span>03</span><p>{t("help.review")}</p></div>
            </div>
            <section className="help-sources">
              <div><h3>{t("sources.platformTitle")}</h3><small>{t("sources.platformCount", { count: helpSources.length })}</small></div>
              <div className="help-source-list">
                {helpSources.map(({ nameKey, host, icon: Icon }) => (
                  <article key={host}>
                    <Icon size={19} />
                    <span><strong>{nameKey === "X" ? "X" : t(nameKey)}</strong><small>{host}</small></span>
                  </article>
                ))}
              </div>
            </section>
          </section>
        </div>
      )}

      {captureOpen && (
        <div className="dialog-layer" role="presentation" onMouseDown={() => setCaptureOpen(false)}>
          <form className="capture-dialog" role="dialog" aria-modal="true" aria-labelledby="capture-title" onSubmit={(event) => { event.preventDefault(); captureMutation.mutate({ url: captureUrl, reviewMode, perspective, outputLanguage }); }} onMouseDown={(event) => event.stopPropagation()}>
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
              { value: "auto_upload", label: t("pipeline.modes.autoUpload"), description: t("pipeline.modes.autoUploadHelp") }
            ]} /></label>
            <label className="settings-field"><span>{t("capture.perspective")}</span><InlineSelect value={perspective} onChange={setPerspective} ariaLabel={t("capture.perspective")} options={(pipelineSettings.data?.perspectives ?? []).map((item) => ({ value: item.id, label: item.label, description: item.description }))} /></label>
            <label className="settings-field"><span>{t("pipeline.outputLanguage")}</span><InlineSelect<OutputLanguage> value={outputLanguage} onChange={setOutputLanguage} ariaLabel={t("pipeline.outputLanguage")} options={(["follow_ui", "source", "zh-CN", "en-US"] as const).map((value) => ({ value, label: t(`pipeline.languages.${value}`), description: t(`pipeline.languagesHelp.${value}`) }))} /></label>
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
