import { lazy, Suspense } from "react";
import { createHashRouter, Navigate, RouterProvider } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { LoadingPanel } from "./components/StatePanel";

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
  return (
    <Suspense fallback={<div className="route-loading"><LoadingPanel /></div>}>
      <RouterProvider router={router} />
    </Suspense>
  );
}
