import { lazy, Suspense } from "react";
import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingPanel } from "./components/StatePanel";

const ArticlePage = lazy(() => import("./pages/ArticlePage").then((module) => ({ default: module.ArticlePage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const PipelinePage = lazy(() => import("./pages/PipelinePage").then((module) => ({ default: module.PipelinePage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const SourcesPage = lazy(() => import("./pages/SourcesPage").then((module) => ({ default: module.SourcesPage })));

export function App() {
  return (
    <HashRouter>
      <Suspense fallback={<div className="route-loading"><LoadingPanel /></div>}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="library" element={<DashboardPage />} />
            <Route path="articles/:articleId" element={<ArticlePage />} />
            <Route path="pipeline" element={<PipelinePage />} />
            <Route path="sources" element={<SourcesPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </Suspense>
    </HashRouter>
  );
}
