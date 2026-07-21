import { Bird, Browser, ChatCircleText, Fire, Globe, Newspaper } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";

const sources = [
  { nameKey: "sources.wechat", host: "mp.weixin.qq.com", icon: ChatCircleText, test: false },
  { nameKey: "sources.zhihu", host: "zhuanlan.zhihu.com", icon: Newspaper, test: false },
  { nameKey: "sources.xiaoheihe", host: "xiaoheihe.cn", icon: Globe, test: false },
  { nameKey: "X", host: "x.com", icon: Bird, test: true }
];

export function SourcesPage() {
  const { t } = useTranslation();
  return (
    <div className="page sources-page">
      <header className="page-header"><div><p className="context-label">{t("sources.eyebrow")}</p><h1>{t("sources.title")}</h1><p>{t("sources.description")}</p></div></header>
      <section className="source-section" aria-labelledby="platforms-title">
        <div className="source-section-heading"><div><p className="source-section-kicker">{t("sources.platformKicker")}</p><h2 id="platforms-title">{t("sources.platformTitle")}</h2></div><span>{t("sources.platformCount", { count: sources.length })}</span></div>
        <div className="source-grid">
          {sources.map(({ nameKey, host, icon: Icon, test }) => (
            <article className="source-item" key={host}>
              <span className="source-icon"><Icon size={24} /></span>
              <div><h3>{nameKey === "X" ? "X" : t(nameKey)}</h3><p>{host}</p></div>
              <span className={test ? "source-state source-test" : "source-state"}>{t(test ? "sources.test" : "sources.supported")}</span>
            </article>
          ))}
        </div>
      </section>
      <section className="source-section crawler-section" aria-labelledby="crawlers-title">
        <div className="source-section-heading"><div><p className="source-section-kicker">{t("sources.crawlerKicker")}</p><h2 id="crawlers-title">{t("sources.crawlerTitle")}</h2></div><span>{t("sources.crawlerCount", { count: 2 })}</span></div>
        <div className="crawler-comparison">
          <article><span><Browser size={25} /></span><div><h3>Crawl4AI</h3><p>{t("sources.crawl4ai")}</p></div><small>{t("sources.localCrawler")}</small></article>
          <article><span><Fire size={25} /></span><div><h3>Firecrawl</h3><p>{t("sources.firecrawl")}</p></div><small>{t("sources.apiCrawler")}</small></article>
        </div>
      </section>
    </div>
  );
}
