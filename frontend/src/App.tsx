import { lazy, Suspense, useEffect } from "react";
import { createHashRouter, Navigate, RouterProvider } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { ErrorPanel, LoadingPanel } from "./components/StatePanel";
import i18n from "./i18n";

const BatchPage = lazy(() => import("./pages/BatchPage").then(module => ({ default: module.BatchPage })));
const SearchPage = lazy(() => import("./pages/SearchPage").then(module => ({ default: module.SearchPage })));

const ArticlePage = lazy(() => import("./pages/ArticlePage").then((module) => ({ default: module.ArticlePage })));
const CollectionPage = lazy(() => import("./pages/CollectionPage").then((module) => ({ default: module.CollectionPage })));
const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const KnowledgePage = lazy(() => import("./pages/KnowledgePage").then((module) => ({ default: module.KnowledgePage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));

const router = createHashRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "batches", element: <BatchPage /> },
      { path: "search", element: <SearchPage /> },
      { path: "library", element: <KnowledgePage /> },
      { path: "collections/:collectionId", element: <CollectionPage /> },
      { path: "articles/:articleId", element: <ArticlePage /> },
      { path: "pipeline", element: <Navigate to="/" replace /> },
      { path: "sources", element: <Navigate to="/" replace /> },
      { path: "review-studio", element: <Navigate to="/settings" replace /> },
      { path: "settings", element: <SettingsPage /> },
      { path: "*", element: <Navigate to="/" replace /> }
    ]
  }
]);

export function App() {
  const queryClient = useQueryClient();
  const auth = useQuery({ queryKey: ["auth-status"], queryFn: api.authStatus, staleTime: 60_000, retry: false });
  useEffect(() => {
    const requireAuth = () => queryClient.setQueryData(["auth-status"], { required: true, authenticated: false });
    window.addEventListener("noosphere-auth-required", requireAuth);
    return () => window.removeEventListener("noosphere-auth-required", requireAuth);
  }, [queryClient]);
  if (auth.isPending) {
    return <div className="route-loading"><LoadingPanel /></div>;
  }
  if (auth.isError) {
    return <main className="login-page"><div className="login-status"><ErrorPanel message={(auth.error as Error).message} /><button className="button-secondary" type="button" onClick={() => void auth.refetch()}>{i18n.resolvedLanguage?.startsWith("zh") ? "重试" : "Retry"}</button></div></main>;
  }
  if (auth.data?.required && !auth.data.authenticated) {
    return <LoginPage />;
  }
  return (
    <Suspense fallback={<div className="route-loading"><LoadingPanel /></div>}>
      <RouterProvider router={router} />
    </Suspense>
  );
}
