import {
  Check,
  CheckCircle,
  Eye,
  EyeSlash,
  FileText,
  FireSimple,
  FloppyDisk,
  Hexagon,
  ImageSquare,
  MoonStars,
  Plus,
  Plugs,
  PlugsConnected,
  Sparkle,
  SpinnerGap,
  Trash,
  WarningCircle,
  WaveSine,
  X
} from "@phosphor-icons/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api";
import { InlineSelect, type InlineSelectOption } from "../components/InlineSelect";
import { SettingsSectionNav } from "../components/SettingsSectionNav";
import { ErrorPanel, LoadingPanel } from "../components/StatePanel";
import type { AIApiFormat, AIProviderSettings, AIProviderType, SettingsUpdate } from "../types";

const MASKED_SECRET = "••••••••••••••••";

const providerTemplates: Record<AIProviderType, Omit<AIProviderSettings, "name" | "apiKeyConfigured">> = {
  kimi: {
    providerType: "kimi",
    apiFormat: "openai_chat",
    model: "",
    apiBase: "https://api.moonshot.cn/v1",
    visionCapable: false
  },
  minimax: {
    providerType: "minimax",
    apiFormat: "openai_chat",
    model: "",
    apiBase: "https://api.minimaxi.com/v1",
    visionCapable: false
  },
  zhipu: {
    providerType: "zhipu",
    apiFormat: "openai_chat",
    model: "",
    apiBase: "https://open.bigmodel.cn/api/paas/v4",
    visionCapable: false
  },
  volcengine: {
    providerType: "volcengine",
    apiFormat: "openai_chat",
    model: "",
    apiBase: "https://ark.cn-beijing.volces.com/api/v3",
    visionCapable: false
  },
  custom: {
    providerType: "custom",
    apiFormat: "openai_chat",
    model: "",
    apiBase: "",
    visionCapable: false
  }
};

const emptySettings: SettingsUpdate = {
  aiProvider: "default",
  imageProvider: "",
  aiProviders: [{
    name: "default",
    providerType: "custom",
    apiFormat: "anthropic",
    model: "",
    apiBase: "",
    apiKeyConfigured: false,
    visionCapable: false
  }],
  crawlerPrimary: "crawl4ai",
  crawlerFallback: "firecrawl",
  firecrawlApiKeyConfigured: false,
  siyuanApiBase: "http://127.0.0.1:6806",
  siyuanParentId: "",
  siyuanTokenConfigured: false,
  localArchiveEnabled: false,
  localArchiveOutputDir: "archive"
};

type TestState = { target: "ai" | "firecrawl" | null; status: "idle" | "checking" | "ok" | "error"; message?: string };

interface SecretFieldProps {
  label: string;
  value: string | undefined;
  configured: boolean;
  placeholder: string;
  help: string;
  revealLabel: string;
  hideLabel: string;
  onChange: (value: string) => void;
  onReveal: () => Promise<string>;
}

function SecretField({
  label,
  value,
  configured,
  placeholder,
  help,
  revealLabel,
  hideLabel,
  onChange,
  onReveal
}: SecretFieldProps) {
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const isMasked = configured && value === undefined;

  useEffect(() => {
    if (value === undefined) setVisible(false);
  }, [value]);

  async function toggleVisibility() {
    if (visible) {
      setVisible(false);
      return;
    }
    if (configured && !value) {
      setLoading(true);
      setError("");
      try {
        onChange(await onReveal());
      } catch (revealError) {
        setError((revealError as Error).message);
        return;
      } finally {
        setLoading(false);
      }
    }
    setVisible(true);
  }

  return (
    <label className="secret-field-label">
      <span>{label}</span>
      <div className="secret-field">
        <input
          type={isMasked || visible ? "text" : "password"}
          value={isMasked ? MASKED_SECRET : value ?? ""}
          readOnly={isMasked}
          onFocus={() => {
            if (isMasked) onChange("");
          }}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          autoComplete="new-password"
        />
        <button
          type="button"
          onMouseDown={(event) => event.preventDefault()}
          onClick={() => void toggleVisibility()}
          aria-label={visible ? hideLabel : revealLabel}
          disabled={loading}
        >
          {loading ? <SpinnerGap className="spin" size={19} /> : visible ? <EyeSlash size={19} /> : <Eye size={19} />}
        </button>
      </div>
      <small>{error || help}</small>
    </label>
  );
}

function ProviderMark({ type }: { type: AIProviderType }) {
  const icons: Record<AIProviderType, ReactNode> = {
    kimi: <MoonStars size={21} weight="fill" />,
    minimax: <WaveSine size={22} weight="bold" />,
    zhipu: <Hexagon size={21} weight="duotone" />,
    volcengine: <FireSimple size={21} weight="fill" />,
    custom: <Plugs size={21} weight="duotone" />
  };
  return <span className={`provider-mark provider-mark-${type}`} aria-hidden="true">{icons[type]}</span>;
}

function endpointSuffix(apiFormat: AIApiFormat) {
  if (apiFormat === "anthropic") return "messages";
  if (apiFormat === "openai_responses") return "responses";
  return "chat/completions";
}

function resolvedEndpoint(apiBase: string, apiFormat: AIApiFormat) {
  if (!apiBase.trim()) return "";
  try {
    const endpoint = new URL(apiBase.trim());
    const cleanPath = endpoint.pathname.replace(/\/+$/, "");
    const suffix = endpointSuffix(apiFormat);
    if (cleanPath.endsWith(`/${suffix}`)) return endpoint.toString();
    endpoint.pathname = cleanPath.endsWith("/v1") ? `${cleanPath}/${suffix}` : `${cleanPath}/v1/${suffix}`;
    return endpoint.toString();
  } catch {
    return apiBase.trim();
  }
}

function apiBaseFromFullEndpoint(value: string, apiFormat: AIApiFormat) {
  try {
    const endpoint = new URL(value.trim());
    const suffix = endpointSuffix(apiFormat);
    const cleanPath = endpoint.pathname.replace(/\/+$/, "");
    if (!cleanPath.endsWith(`/${suffix}`)) return null;
    endpoint.pathname = cleanPath.slice(0, -(`/${suffix}`.length)) || "/";
    endpoint.search = "";
    endpoint.hash = "";
    return endpoint.toString().replace(/\/$/, "");
  } catch {
    return null;
  }
}

export function SettingsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: api.getSettings,
    staleTime: 0,
    refetchOnMount: "always"
  });
  const [form, setForm] = useState<SettingsUpdate>(emptySettings);
  const [selectedProviderName, setSelectedProviderName] = useState(emptySettings.aiProvider);
  const [addingProvider, setAddingProvider] = useState(false);
  const [newProviderType, setNewProviderType] = useState<AIProviderType>("kimi");
  const [newProviderName, setNewProviderName] = useState("");
  const [providerError, setProviderError] = useState("");
  const [providerPendingDelete, setProviderPendingDelete] = useState<string | null>(null);
  const [endpointMessage, setEndpointMessage] = useState("");
  const [openSelect, setOpenSelect] = useState<string | null>(null);
  const [testState, setTestState] = useState<TestState>({ target: null, status: "idle" });

  useEffect(() => {
    if (!settingsQuery.data) return;
    setForm(settingsQuery.data);
    setSelectedProviderName(settingsQuery.data.aiProvider);
  }, [settingsQuery.data]);

  const selectedProvider = useMemo(
    () => form.aiProviders.find((provider) => provider.name === selectedProviderName) ?? form.aiProviders[0],
    [form.aiProviders, selectedProviderName]
  );
  const settingsChanged = useMemo(
    () => Boolean(settingsQuery.data && JSON.stringify(form) !== JSON.stringify(settingsQuery.data)),
    [form, settingsQuery.data]
  );

  const providerTypeOptions = useMemo<InlineSelectOption<AIProviderType>[]>(() => (
    (Object.keys(providerTemplates) as AIProviderType[]).map((type) => ({
      value: type,
      label: <span className="provider-option-label"><ProviderMark type={type} />{t(`settings.providerTypes.${type}`)}</span>,
      description: t(`settings.providerTypeDescriptions.${type}`)
    }))
  ), [t]);

  const apiFormatOptions = useMemo<InlineSelectOption<AIApiFormat>[]>(() => [
    { value: "openai_chat", label: "OpenAI Chat Completions", description: t("settings.openaiChatHelp") },
    { value: "openai_responses", label: "OpenAI Responses", description: t("settings.openaiResponsesHelp") },
    { value: "anthropic", label: "Anthropic Messages", description: t("settings.anthropicHelp") }
  ], [t]);

  const saveMutation = useMutation({
    mutationFn: api.updateSettings,
    onSuccess: (data) => {
      setForm(data);
      queryClient.setQueryData(["settings"], data);
      if (!data.aiProviders.some((provider) => provider.name === selectedProviderName)) {
        setSelectedProviderName(data.aiProvider);
      }
    }
  });

  const activateProviderMutation = useMutation({
    mutationFn: ({ providerName, settings }: { providerName: string; settings: SettingsUpdate }) =>
      api.activateAIProvider(providerName, settings),
    onSuccess: async (data) => {
      setForm(data);
      setSelectedProviderName(data.aiProvider);
      queryClient.setQueryData(["settings"], data);
      await queryClient.refetchQueries({ queryKey: ["settings"], exact: true, type: "active" });
    }
  });

  function update<K extends keyof SettingsUpdate>(key: K, value: SettingsUpdate[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function updateProvider<K extends keyof AIProviderSettings>(key: K, value: AIProviderSettings[K]) {
    setForm((current) => ({
      ...current,
      aiProviders: current.aiProviders.map((provider) => provider.name === selectedProvider?.name ? { ...provider, [key]: value } : provider)
    }));
  }

  function selectPrimaryCrawler(primary: string) {
    setForm((current) => ({
      ...current,
      crawlerPrimary: primary,
      crawlerFallback: current.crawlerFallback ? (primary === "firecrawl" ? "crawl4ai" : "firecrawl") : ""
    }));
  }

  function openProviderCreator() {
    setAddingProvider((value) => !value);
    setProviderError("");
    if (!newProviderName) setNewProviderName(t("settings.defaultProviderNames.kimi"));
  }

  function addProvider() {
    const name = newProviderName.trim();
    if (!name) {
      setProviderError(t("settings.providerNameRequired"));
      return;
    }
    if (form.aiProviders.some((provider) => provider.name.toLowerCase() === name.toLowerCase())) {
      setProviderError(t("settings.providerNameDuplicate"));
      return;
    }
    const provider: AIProviderSettings = {
      name,
      ...providerTemplates[newProviderType],
      apiKeyConfigured: false
    };
    setForm((current) => ({ ...current, aiProviders: [...current.aiProviders, provider] }));
    setSelectedProviderName(name);
    setAddingProvider(false);
    setNewProviderName("");
    setProviderError("");
    setEndpointMessage("");
  }

  function deleteProvider(name: string) {
    if (form.aiProviders.length <= 1) return;
    const remaining = form.aiProviders.filter((provider) => provider.name !== name);
    const nextActive = form.aiProvider === name ? remaining[0].name : form.aiProvider;
    setForm((current) => ({
      ...current,
      aiProviders: remaining,
      aiProvider: nextActive,
      imageProvider: current.imageProvider === name ? "" : current.imageProvider
    }));
    if (selectedProviderName === name) setSelectedProviderName(nextActive);
    setProviderPendingDelete(null);
    setOpenSelect(null);
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    saveMutation.mutate(form);
  }

  async function testService(target: "ai" | "firecrawl") {
    setTestState({ target, status: "checking" });
    try {
      await api.testSettingsService(target, target === "ai" ? selectedProvider?.name : undefined, form);
      setTestState({ target, status: "ok" });
    } catch (error) {
      setTestState({ target, status: "error", message: (error as Error).message });
    }
  }

  function testResult(target: "ai" | "firecrawl") {
    if (testState.target !== target || testState.status === "idle" || testState.status === "checking") return null;
    if (testState.status === "ok") return <span className="connection-result connection-ok"><CheckCircle size={18} />{t("settings.connectionPassed")}</span>;
    return <span className="connection-result connection-error"><WarningCircle size={18} />{testState.message || t("settings.unavailable")}</span>;
  }

  if (settingsQuery.isLoading) return <div className="page"><LoadingPanel label={t("common.loadingSettings")} /></div>;
  if (settingsQuery.isError) return <div className="page"><ErrorPanel message={(settingsQuery.error as Error).message} /></div>;

  const fallbackCrawler = form.crawlerPrimary === "firecrawl" ? "crawl4ai" : "firecrawl";
  const crawlerOptions: InlineSelectOption<string>[] = [
    { value: "crawl4ai", label: "Crawl4AI", description: t("settings.crawl4aiOptionHelp") },
    { value: "firecrawl", label: "Firecrawl", description: t("settings.firecrawlOptionHelp") }
  ];
  const fallbackOptions: InlineSelectOption<string>[] = [
    { value: fallbackCrawler, label: fallbackCrawler === "firecrawl" ? "Firecrawl" : "Crawl4AI" },
    { value: "", label: t("common.disabled"), description: t("settings.disabledFallbackHelp") }
  ];

  return (
    <div className="page settings-page">
      <header className="page-header">
        <div><p className="context-label">{t("settings.eyebrow")}</p><h1>{t("settings.title")}</h1><p>{t("settings.description")}</p></div>
      </header>
      <div className="settings-content-layout">
      <SettingsSectionNav />
      <form className="settings-form" onSubmit={submit}>
        <section className="settings-group provider-settings-group" id="settings-ai">
          <div className="group-heading group-heading-action">
            <div><h2>{t("settings.aiTitle")}</h2><p>{t("settings.aiDescription")}</p></div>
            <button className="button-secondary compact-button" type="button" onClick={openProviderCreator} aria-expanded={addingProvider}>
              {addingProvider ? <X size={16} /> : <Plus size={16} />}{addingProvider ? t("common.cancel") : t("settings.addProvider")}
            </button>
          </div>

          {addingProvider && (
            <div className="new-provider-panel">
              <label>
                <span>{t("settings.providerTemplate")}</span>
                <InlineSelect
                  value={newProviderType}
                  options={providerTypeOptions}
                  onChange={(value) => {
                    setNewProviderType(value);
                    setNewProviderName(t(`settings.defaultProviderNames.${value}`));
                    setProviderError("");
                  }}
                  open={openSelect === "provider-template"}
                  onOpenChange={(open) => setOpenSelect(open ? "provider-template" : null)}
                  ariaLabel={t("settings.providerTemplate")}
                />
              </label>
              <label>
                <span>{t("settings.providerName")}</span>
                <input value={newProviderName} onChange={(event) => { setNewProviderName(event.target.value); setProviderError(""); }} placeholder={t("settings.providerNamePlaceholder")} />
              </label>
              <button className="button-primary new-provider-submit" type="button" onClick={addProvider}>{t("settings.createProvider")}</button>
              {providerError && <p className="provider-error" role="alert">{providerError}</p>}
            </div>
          )}

          <div className="provider-workspace">
            <aside className="provider-list-panel" aria-label={t("settings.providerList") }>
              <div className="provider-list-heading">
                <strong>{t("settings.providerList")}</strong>
                <span>{t("settings.providerCount", { count: form.aiProviders.length })}</span>
              </div>
              <div className="provider-list">
                {form.aiProviders.map((provider) => {
                  const isActive = provider.name === form.aiProvider;
                  const isSelected = provider.name === selectedProvider?.name;
                  return (
                    <div className={`provider-card${isSelected ? " provider-card-selected" : ""}`} key={provider.name}>
                      <button
                        className="provider-card-select"
                        type="button"
                        aria-pressed={isSelected}
                        onClick={() => {
                          setSelectedProviderName(provider.name);
                          activateProviderMutation.reset();
                          setProviderPendingDelete(null);
                          setEndpointMessage("");
                          setOpenSelect(null);
                          setTestState({ target: null, status: "idle" });
                        }}
                      >
                        <ProviderMark type={provider.providerType} />
                        <span className="provider-card-copy">
                          <strong>{provider.name}</strong>
                          <span className="provider-card-meta">
                            <small>{t(`settings.providerTypes.${provider.providerType}`)}</small>
                            <span className="provider-capability-badge"><FileText size={11} />{t("settings.textCapabilityBadge")}</span>
                            {provider.visionCapable && <span className="provider-capability-badge provider-capability-image"><ImageSquare size={11} />{t("settings.imageCapabilityBadge")}</span>}
                          </span>
                        </span>
                        {isActive && <span className="provider-active-badge"><Check size={13} weight="bold" />{t("settings.active")}</span>}
                      </button>
                      <button
                        className={`provider-delete${providerPendingDelete === provider.name ? " provider-delete-confirm" : ""}`}
                        type="button"
                        disabled={form.aiProviders.length <= 1}
                        aria-label={providerPendingDelete === provider.name ? t("settings.confirmDeleteProvider", { name: provider.name }) : t("settings.deleteProvider", { name: provider.name })}
                        title={form.aiProviders.length <= 1 ? t("settings.keepOneProvider") : t("settings.deleteProvider", { name: provider.name })}
                        onClick={() => {
                          if (providerPendingDelete === provider.name) deleteProvider(provider.name);
                          else setProviderPendingDelete(provider.name);
                        }}
                      >
                        <Trash size={16} />
                        {providerPendingDelete === provider.name && <span>{t("common.confirm")}</span>}
                      </button>
                    </div>
                  );
                })}
              </div>
            </aside>

            <div className="provider-detail-stack">
            {selectedProvider && (
              <div className="provider-editor" key={selectedProvider.name}>
                <div className="provider-editor-heading">
                  <div className="provider-editor-identity"><ProviderMark type={selectedProvider.providerType} /><div><h3>{selectedProvider.name}</h3><p>{t(`settings.providerTypeDescriptions.${selectedProvider.providerType}`)}</p></div></div>
                  {selectedProvider.name === form.aiProvider && <span className="active-provider-label"><CheckCircle size={17} weight="fill" />{t("settings.activeProvider")}</span>}
                </div>

                <div className="field-grid provider-top-fields">
                  <label>
                    <span>{t("settings.apiFormat")}</span>
                    <InlineSelect
                      value={selectedProvider.apiFormat}
                      options={apiFormatOptions}
                      onChange={(value) => { updateProvider("apiFormat", value); setEndpointMessage(""); }}
                      open={openSelect === "api-format"}
                      onOpenChange={(open) => setOpenSelect(open ? "api-format" : null)}
                      ariaLabel={t("settings.apiFormat")}
                    />
                  </label>
                </div>

                <label><span>{t("settings.model")}</span><input value={selectedProvider.model} onChange={(event) => updateProvider("model", event.target.value)} placeholder={t("settings.modelPlaceholder")} /><small>{t("settings.modelHelp")}</small></label>
                <label>
                  <span>{t("settings.apiEndpoint")}</span>
                  <input type="url" value={selectedProvider.apiBase} onChange={(event) => { updateProvider("apiBase", event.target.value); setEndpointMessage(""); }} placeholder="https://api.example.com/v1" />
                  <small>{t("settings.apiEndpointHelp")}</small>
                </label>
                <div className="resolved-endpoint">
                  <div><span>{t("settings.resolvedEndpoint")}</span><code>{resolvedEndpoint(selectedProvider.apiBase, selectedProvider.apiFormat) || t("settings.endpointPending")}</code></div>
                  <button
                    className="button-secondary compact-button"
                    type="button"
                    onClick={() => {
                      const parsed = apiBaseFromFullEndpoint(selectedProvider.apiBase, selectedProvider.apiFormat);
                      if (!parsed) {
                        setEndpointMessage(t("settings.fullEndpointNotDetected"));
                        return;
                      }
                      updateProvider("apiBase", parsed);
                      setEndpointMessage(t("settings.fullEndpointParsed"));
                    }}
                  >
                    <Sparkle size={15} />{t("settings.parseFullEndpoint")}
                  </button>
                </div>
                {endpointMessage && <p className="endpoint-message" role="status">{endpointMessage}</p>}

                <SecretField
                  label={t("settings.apiKey")}
                  value={selectedProvider.apiKey}
                  configured={selectedProvider.apiKeyConfigured}
                  placeholder={t("settings.enterApiKey")}
                  help={t("settings.secretHelp")}
                  revealLabel={t("settings.showApiKey")}
                  hideLabel={t("settings.hideApiKey")}
                  onChange={(value) => updateProvider("apiKey", value)}
                  onReveal={async () => (await api.getSettingsSecret("ai", selectedProvider.name)).secret}
                />
                <label className="provider-capability-toggle">
                  <input
                    type="checkbox"
                    checked={selectedProvider.visionCapable}
                    onChange={(event) => {
                      const visionCapable = event.target.checked;
                      setForm((current) => ({
                        ...current,
                        imageProvider: visionCapable
                          ? current.imageProvider || selectedProvider.name
                          : current.imageProvider === selectedProvider.name ? "" : current.imageProvider,
                        aiProviders: current.aiProviders.map((provider) => provider.name === selectedProvider.name
                          ? { ...provider, visionCapable }
                          : provider)
                      }));
                    }}
                  />
                  <span><strong>{t("settings.visionCapability")}</strong><small>{t("settings.visionCapabilityHelp")}</small></span>
                </label>
                <div className="provider-action-row">
                  <button className="button-secondary provider-test-button" type="button" onClick={() => void testService("ai")} disabled={testState.status === "checking"}><PlugsConnected size={18} />{testState.target === "ai" && testState.status === "checking" ? t("settings.checking") : t("settings.testProvider")}</button>
                  <div className="provider-action-feedback" aria-live="polite">
                    {activateProviderMutation.isError
                      ? <span className="connection-result connection-error" role="alert"><WarningCircle size={18} />{(activateProviderMutation.error as Error).message}</span>
                      : activateProviderMutation.isSuccess
                        ? <span className="connection-result connection-ok" role="status"><CheckCircle size={18} />{t("settings.providerActivated")}</span>
                        : testResult("ai")}
                  </div>
                  <button
                    className="button-primary provider-activate-button"
                    type="button"
                    disabled={saveMutation.isPending || activateProviderMutation.isPending || (selectedProvider.name === form.aiProvider && !settingsChanged)}
                    onClick={() => activateProviderMutation.mutate({ providerName: selectedProvider.name, settings: form })}
                  >
                    {activateProviderMutation.isPending ? <SpinnerGap className="spin" size={18} /> : <CheckCircle size={18} />}
                    {selectedProvider.name === form.aiProvider
                      ? settingsChanged ? t("settings.saveProviderChanges") : t("settings.activeProvider")
                      : activateProviderMutation.isPending
                        ? t("settings.activatingProvider")
                        : t("settings.setActive")}
                  </button>
                </div>
              </div>
            )}
              <div className="image-provider-role">
                <span className="image-provider-role-icon"><ImageSquare size={21} /></span>
                <div className="image-provider-role-copy"><strong>{t("settings.imageProviderTitle")}</strong><p>{t("settings.imageProviderDescription")}</p></div>
                <div className="image-provider-role-select">
                  <InlineSelect
                    value={form.imageProvider}
                    onChange={(imageProvider) => update("imageProvider", imageProvider)}
                    ariaLabel={t("settings.imageProviderTitle")}
                    options={[
                      { value: "", label: t("settings.imageProviderDisabled"), description: t("settings.imageProviderDisabledHelp") },
                      ...form.aiProviders.filter((provider) => provider.visionCapable).map((provider) => ({
                        value: provider.name,
                        label: <span className="image-provider-option"><ProviderMark type={provider.providerType} /><span>{provider.name}</span></span>,
                        description: provider.model || t("settings.modelPending")
                      }))
                    ]}
                  />
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="settings-group" id="settings-crawlers">
          <div className="group-heading"><h2>{t("settings.crawlersTitle")}</h2><p>{t("settings.crawlersDescription")}</p></div>
          <div className="field-grid two-columns crawler-fields">
            <label className="field-with-helper">
              <span>{t("settings.primaryCrawler")}</span>
              <InlineSelect
                value={form.crawlerPrimary}
                options={crawlerOptions}
                onChange={selectPrimaryCrawler}
                open={openSelect === "primary-crawler"}
                onOpenChange={(open) => setOpenSelect(open ? "primary-crawler" : null)}
                ariaLabel={t("settings.primaryCrawler")}
              />
              <small>{t("settings.primaryHelp")}</small>
            </label>
            <label className="field-with-helper">
              <span>{t("settings.fallbackCrawler")}</span>
              <InlineSelect
                value={form.crawlerFallback ? fallbackCrawler : ""}
                options={fallbackOptions}
                onChange={(value) => update("crawlerFallback", value)}
                open={openSelect === "fallback-crawler"}
                onOpenChange={(open) => setOpenSelect(open ? "fallback-crawler" : null)}
                ariaLabel={t("settings.fallbackCrawler")}
              />
              <small>{t("settings.fallbackHelp")}</small>
            </label>
          </div>
          {(form.crawlerPrimary === "firecrawl" || form.crawlerFallback === "firecrawl") && (
            <div className="crawler-secret-panel">
              <SecretField
                label={t("settings.firecrawlKey")}
                value={form.firecrawlApiKey}
                configured={form.firecrawlApiKeyConfigured}
                placeholder={t("settings.enterFirecrawlKey")}
                help={t("settings.secretHelp")}
                revealLabel={t("settings.showFirecrawlKey")}
                hideLabel={t("settings.hideFirecrawlKey")}
                onChange={(value) => update("firecrawlApiKey", value)}
                onReveal={async () => (await api.getSettingsSecret("firecrawl")).secret}
              />
              <div className="inline-test-row"><button className="button-secondary" type="button" onClick={() => void testService("firecrawl")} disabled={testState.status === "checking"}><PlugsConnected size={18} />{testState.target === "firecrawl" && testState.status === "checking" ? t("settings.checking") : t("settings.testFirecrawl")}</button>{testResult("firecrawl")}</div>
            </div>
          )}
        </section>

        <section className="settings-group" id="settings-destinations">
          <div className="group-heading"><h2>{t("settings.destinationsTitle")}</h2><p>{t("settings.destinationsDescription")}</p></div>
          <div className="field-grid two-columns">
            <label><span>{t("settings.siyuanEndpoint")}</span><input type="url" value={form.siyuanApiBase} onChange={(event) => update("siyuanApiBase", event.target.value)} /></label>
            <label><span>{t("settings.siyuanParent")}</span><input value={form.siyuanParentId} onChange={(event) => update("siyuanParentId", event.target.value)} /></label>
          </div>
          <SecretField
            label={t("settings.siyuanToken")}
            value={form.siyuanToken}
            configured={form.siyuanTokenConfigured}
            placeholder={t("settings.enterToken")}
            help={t("settings.secretHelp")}
            revealLabel={t("settings.showSiyuanToken")}
            hideLabel={t("settings.hideSiyuanToken")}
            onChange={(value) => update("siyuanToken", value)}
            onReveal={async () => (await api.getSettingsSecret("siyuan")).secret}
          />
          <label className="toggle-row"><span><strong>{t("settings.localArchive")}</strong><small>{t("settings.localArchiveHelp")}</small></span><input type="checkbox" checked={form.localArchiveEnabled} onChange={(event) => update("localArchiveEnabled", event.target.checked)} /></label>
          {form.localArchiveEnabled && <label><span>{t("settings.archiveDirectory")}</span><input value={form.localArchiveOutputDir} onChange={(event) => update("localArchiveOutputDir", event.target.value)} /></label>}
        </section>

        <div className="settings-actions save-only-actions">
          <span />
          <button className="button-primary" type="submit" disabled={saveMutation.isPending || activateProviderMutation.isPending}><FloppyDisk size={18} />{saveMutation.isPending ? t("settings.saving") : t("settings.save")}</button>
        </div>
        {saveMutation.isSuccess && <p className="save-message success-message" role="status"><CheckCircle size={18} />{t("settings.saved")}</p>}
        {saveMutation.isError && <p className="save-message error-message" role="alert"><WarningCircle size={18} />{(saveMutation.error as Error).message}</p>}
      </form>
      </div>
    </div>
  );
}
